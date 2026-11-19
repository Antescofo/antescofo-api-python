"""Read organization usage and recent jobs without creating or charging a new job."""

import json

from antescofo_api import AntescofoClient


def main():
    with AntescofoClient() as client:
        print(json.dumps(client.usage.get(), indent=2))
        for job in client.jobs.list(limit=10, module="performance_analyzer").results:
            print(job.id, job.status, job.audio_duration_seconds)


if __name__ == "__main__":
    main()
