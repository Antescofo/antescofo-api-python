"""Create one real job, wait, and save its analysis. Requires configured API access."""

import argparse
import json
from pathlib import Path

from antescofo_api import AntescofoClient, AntescofoError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("outputs/result.json"))
    args = parser.parse_args()
    try:
        with AntescofoClient() as client:
            result = client.performance_analyzer.analyze(audio=args.audio, score=args.score)
    except AntescofoError as error:
        parser.exit(1, f"{error}\nExisting job ID: {error.job_id or 'not available'}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {args.output}")
    print(json.dumps(result.get("assessment"), indent=2))


if __name__ == "__main__":
    main()
