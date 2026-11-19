"""Create and upload one real job without waiting; save its ID to resume later."""

import argparse
from pathlib import Path

from antescofo_api import AntescofoClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    args = parser.parse_args()
    with AntescofoClient() as client:
        job = client.performance_analyzer.submit(audio=args.audio, score=args.score)
        print(f"Job ID: {job.id}")
        print(f"Resume: python examples/resume.py {job.id}")


if __name__ == "__main__":
    main()
