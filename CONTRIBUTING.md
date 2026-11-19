# Contributing

This repository contains the Python API client, its examples, and offline tests.
For API access and integration documentation, visit
[Antescofo Platform](https://platform.antescofo.com/).

## Local Setup

Install Python 3.10 or newer and [uv](https://docs.astral.sh/uv/), then run:

```sh
uv sync --group dev
```

## Checks

```sh
uv run pytest --cov --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

Automated tests mock HTTP and reject unregistered requests. They do not require
API credentials, upload recordings, or consume job allowance. CI runs these checks
on Python 3.10, 3.12, and 3.14 and builds distributions without publishing them.

## Optional Integration Check

Use your own API access and recordings you are authorized to upload. Unlike the
normal client examples, the smoke-test helper deliberately requires an explicit
`--base-url` so that a live test cannot unintentionally select the default service.
Choose the API origin provided for the environment you intend to test, then run:

```sh
uv run python examples/smoke_test.py \
  --base-url '<API origin to test>' \
  --audio /path/to/audio.mp3 --score /path/to/score.xml \
  --output-dir /path/to/smoke-results --create-job
```

This creates **one real job and consumes allowance**. The script prompts privately
for a key if `ANTESCOFO_API_KEY` is absent. It records the job ID, verifies result
retrieval and usage, and saves a report without credentials or signed URLs.

To resume an existing job, use a new output directory and replace `--create-job`
with `--resume-job-id JOB_UUID`. Recovery does not create or upload another job.
Do not run live integration checks in CI.

## Changes And Bug Reports

- Keep examples and documentation consistent with public method signatures.
- Preserve detailed analysis fields rather than recreating assessment logic.
- Never retry creation automatically: a lost response may still represent an
  accepted job. Preserve job IDs so callers can recover without duplicate usage.
- Keep API credentials isolated from signed storage transfers.
- Do not include API keys, signed URLs, personal data, or real recordings in
  commits or issues. Share a minimal reproducible example with sensitive details
  removed; contact research@antescofo.com for assistance with private data.
