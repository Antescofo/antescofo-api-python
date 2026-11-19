"""Wait for and download an existing job. Never creates another job."""

import argparse
import json
from pathlib import Path

from antescofo_api import AntescofoClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    parser.add_argument("--output", type=Path, default=Path("outputs/result.json"))
    args = parser.parse_args()
    with AntescofoClient() as client:
        client.jobs.wait(args.job_id)
        result = client.jobs.get_result(args.job_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
