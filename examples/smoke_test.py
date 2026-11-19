"""Verify an integration with one new job, or recover an existing job without resubmission."""

import argparse
import getpass
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from antescofo_api import AntescofoClient, AntescofoError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-job", action="store_true", help="Authorize one real job")
    mode.add_argument("--resume-job-id", help="Recover an existing job without creating one")
    args = parser.parse_args()
    # Refuse to overwrite any previous submission/recovery record.
    args.output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    key = os.environ.get("ANTESCOFO_API_KEY") or getpass.getpass("Antescofo API key: ")
    report = {
        "base_url": args.base_url,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "created_by_this_run": args.create_job,
        "inputs": {
            role: {"name": path.name, "sha256": digest(path)}
            for role, path in (("audio", args.audio), ("score", args.score))
        },
    }
    started = time.monotonic()
    job = None
    try:
        save(args.output_dir / "report.json", report)
        with AntescofoClient(key, base_url=args.base_url) as client:
            report["usage_before"] = client.usage.get()
            save(args.output_dir / "report.json", report)
            job = (
                client.performance_analyzer.submit(audio=args.audio, score=args.score)
                if args.create_job
                else client.jobs.get(args.resume_job_id)
            )
            print(f"Job {job.id}; save this ID to resume without resubmitting.", flush=True)
            report["job"] = job.to_dict()
            save(args.output_dir / "report.json", report)
            client.jobs.wait(job.id)
            result = client.jobs.get_result(job.id)
            report["job"] = client.jobs.get(job.id).to_dict()
            report["listed"] = any(
                item.id == job.id for item in client.jobs.list(limit=100).results
            )
            report["usage_after"] = client.usage.get()
            save(args.output_dir / "result.json", result)
            report["result_summary"] = {
                "events": len(result["alignment_interop"]),
                "notes": sum(len(event.get("notes", [])) for event in result["alignment_interop"]),
                "assessment": result.get("assessment"),
            }
            if (
                args.create_job
                and report["usage_after"]["jobs"] < report["usage_before"]["jobs"] + 1
            ):
                raise ValueError("Submitted job was not reflected in usage; check the report.")
    except (AntescofoError, ValueError, OSError) as error:
        report["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "job_id": getattr(error, "job_id", None) or (job.id if job else None),
        }
        save(args.output_dir / "report.json", report)
        parser.exit(1, f"{error}\nInspect report.json and recover the same job; do not resubmit.\n")
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    save(args.output_dir / "report.json", report)
    print(json.dumps(report, indent=2))


def save(path, data):
    with open(path, "w", encoding="utf-8", opener=private_file) as output:
        json.dump(data, output, indent=2)
        output.write("\n")


def private_file(path, flags):
    return os.open(path, flags, 0o600)


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


if __name__ == "__main__":
    main()
