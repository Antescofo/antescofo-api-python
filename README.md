# Antescofo API for Python

**Website: [platform.antescofo.com](https://platform.antescofo.com/)**

[API documentation](https://platform.antescofo.com/api-docs/) |
[Request API access](https://platform.antescofo.com/licensing/#contact)

A synchronous Python client for Antescofo music intelligence APIs. Analyze a piano
performance against a MusicXML score, retrieve note-by-note alignment and
assessment, and inspect your organization's job usage from notebooks, scripts,
and data-processing pipelines.

This package transfers files and orchestrates remote jobs. It does not contain or
run Antescofo's analysis engines. Python 3.10 or newer is required.

## Installation

We recommend [uv](https://docs.astral.sh/uv/getting-started/installation/) for
project setup, dependency management, and running your integration.
For a new project:

```sh
uv init --python 3.12 antescofo-analysis
cd antescofo-analysis
uv add "antescofo-api @ git+https://github.com/Antescofo/antescofo-api-python.git@main"
```

For an existing uv project, run only the `uv add` command from its directory.
uv manages the project environment and records the resolved dependency in
`uv.lock`. Run your integration with `uv run python analyze.py`.

If GitHub authentication is required, configure your Git credentials or SSH
access as described in [uv's Git authentication guide](https://docs.astral.sh/uv/concepts/authentication/git/).
GitHub credentials are separate from your Antescofo API key; never put tokens
in dependency URLs or project files.

From a checkout of this repository, install with `uv sync` and run the examples
with `uv run python examples/analyze.py ...`.

<details>
<summary>Using pip in an existing Python environment</summary>

```sh
python -m pip install 'git+https://github.com/Antescofo/antescofo-api-python.git@main'
```

For a local checkout, use `python -m pip install .`.

</details>

The distribution name is `antescofo-api`; the import is `antescofo_api`.
The only runtime dependency is Requests.
The package is not currently published to PyPI.

## Configuration

Obtain API access through [Antescofo Platform](https://platform.antescofo.com/licensing/#contact).
Once access is granted, select your organization in
[Account > API Access](https://platform.antescofo.com/account/) and create an API
key. Save its secret when it is shown; it cannot be retrieved later. Use the full
key, not a website login token or password.

**Only your API key is required.** The client connects to the Antescofo API
automatically, and your key selects your organization. No Base URL or organization
ID is needed for normal usage.

```sh
read -r -s -p 'Antescofo API key: ' ANTESCOFO_API_KEY
printf '\n'
export ANTESCOFO_API_KEY
```

The prompt above is for Bash. Do not paste credentials into examples, source,
notebooks, shell history, or Git. The library does not load `.env` automatically.
Alternatively, pass `api_key=` to `AntescofoClient` instead of using the environment.
An explicit argument takes precedence over the environment variable.

<details>
<summary>Optional: use another API environment</summary>

The default API origin is `https://api.platform.metronaut.app`. If Antescofo has
provided access to another environment, use its Base URL from Account > API
Access. Configure `ANTESCOFO_API_BASE_URL` before running the same examples, or
pass `base_url=` to the constructor. This is not required for normal usage.

Precedence is `base_url=` argument, then `ANTESCOFO_API_BASE_URL`, then the default.
Supply an origin only, without `/v1` or another path: the client appends `/v1/`
to API requests. For example, job creation uses `POST /v1/jobs/`.
Do not use the Platform website or browser-login URL.

Credentials must match the selected environment. The client never tries another
environment after a failure. To return to the default API, remove the override;
an explicitly blank or unsafe override is rejected before any network request.

</details>

Version 0.3.0 or newer provides automatic API selection. Update an existing uv
installation with `uv sync --upgrade-package antescofo-api` (or reinstall with pip).
See [CHANGELOG.md](CHANGELOG.md) for version history.

## Analyze A Performance

```python
import json
from pathlib import Path

from antescofo_api import AntescofoClient

with AntescofoClient() as client:
    result = client.performance_analyzer.analyze(
        audio="performance.mp3",
        score="score.musicxml",
        timeout_seconds=1800,
        poll_interval_seconds=3,
    )

Path("result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(result["assessment"])
```

`analyze` creates exactly one job, PUTs the original inputs to signed URLs, polls,
and downloads the result. Supported inputs are MP3/WAV and `.xml`/`.musicxml`.
Files are streamed during upload, never transcoded or modified locally.

Do not supply an audio duration: `analyze` and `submit` do not accept a duration
override or send `file_duration`. Audio decoding and duration measurement belong
to the service after upload. `Job.audio_duration_seconds` preserves the API's
`file_duration` when returned; it can be `None` and is not a local estimate or a
compute-time measurement. Duration-based usage totals may be incomplete when
the service has not recorded a duration. Accepted jobs still count toward your
job allowance.

The result is a dictionary with `alignment_interop` and `assessment`. Detailed
events, missing/wrong/extra notes, observed onsets, optional onset deviations,
velocity, probability, and future fields are preserved rather than simplified.
Missing notes have no observed onset; an absent deviation is not a zero deviation.

## Submit And Resume

```python
from antescofo_api import AntescofoClient

with AntescofoClient() as client:
    job = client.performance_analyzer.submit(audio="performance.mp3", score="score.xml")
    print(str(job.id))  # Save this UUID string before doing other work.
    print(client.jobs.get(job.id).status)
    client.jobs.wait(job.id, timeout_seconds=1800)
    result = client.jobs.get_result(job.id)
```

`submit` returns after uploads, not after computation. It returns the creation
snapshot (normally `pending`); call `jobs.get` for the current status. A new
process can resume with the saved ID without uploading or creating a job again.

`Job.id` is a `uuid.UUID` object. `jobs.get`, `jobs.wait`, and `jobs.get_result`
accept `str | UUID`: pass `job.id` directly or pass a saved UUID string.
Use `str(job.id)` when saving the ID as text or comparing it with a string.
`job.to_dict()` exports the ID as a canonical string under `"uuid"` and omits
signed URLs, so the snapshot can be saved with `json.dumps(job.to_dict())`.

| Method | Behavior |
| --- | --- |
| `performance_analyzer.analyze(...)` | Submit, upload, wait, return analysis JSON |
| `performance_analyzer.submit(...)` | Submit and upload, return a `Job` |
| `performance_analyzer.upload_inputs(job, audio=..., score=...)` | Retry input PUTs with the original creation handle |
| `jobs.get(job_id)` | Return a current `Job` snapshot |
| `jobs.wait(job_id, timeout_seconds=1800, poll_interval_seconds=3)` | Poll sequentially and return the successful `Job` |
| `jobs.get_result(job_id)` | Fetch a fresh result URL and return JSON; does not wait |
| `jobs.list(limit=20, offset=0, ...)` | Return a `JobPage` with `count`, `results`, `next`, `previous` |
| `usage.get()` | Return organization usage reported by the API |

`jobs.list` supports `module`, `status`, `created_from`, and `created_to`
(ISO timestamps; `created_to` is exclusive). It fetches one page and never
automatically follows server-provided pagination URLs. Use offsets for more pages.

`usage.get()` includes `jobs`, `total_file_seconds`, module allowances, concurrency,
and the reporting period. Usage is shared across organization members, while job
history is restricted to jobs visible to the authenticated member. Null quota
limits mean unlimited. Submitted audio reflects duration recorded by the service
and may be incomplete when a duration is unavailable; accepted jobs consume
allowance even if uploads or analysis later fail.

## Errors And Recovery

All library errors inherit from `AntescofoError`. Errors after creation normally
include `job_id` as a UUID string (or `None` when unknown); local validation errors
are standard `ValueError`/`OSError`.

- `AuthenticationError`: API 401/403; check the key, membership, and environment.
- `QuotaExceededError`: API 429; inspect `.code` and `.details` for admission limits.
- `APIError`: other API HTTP failures; retains `.status_code`, `.code`, `.details`.
- `SubmissionError`: the creation response was lost. A job may exist; inspect
  `jobs.list()` before submitting again. There is no creation idempotency key yet.
- `UploadError`: preserve `.job` and retry `upload_inputs(error.job, ...)` with the
  same original files. The handle contains private signed URLs, currently valid
  for one hour. Do not retry uploads after processing has already started.
- `JobFailedError` / `JobCanceledError`: terminal states, with `.job` details.
- `JobTimeoutError`: waiting stopped; `.last_job` contains the last known snapshot.
  The server job continues. Resume `wait`/`get_result` for the same ID.
- `ResultUnavailableError`: processing or its result is not ready; retry the same ID.
- `TransportError` / `ProtocolError`: network or response-contract problems;
  recover the existing job rather than blindly calling `analyze` again.

The client never automatically retries HTTP requests or creates replacement jobs.
API credentials are sent only to the configured API origin, never to signed
storage URLs. Requests do not inherit ambient cookies or `.netrc` authentication;
redirects are refused. HTTPS is required except on loopback development servers.
Environment proxy and CA settings are supported. Do not enable raw HTTP debug
logging around secrets. A client is synchronous and not thread-safe.

`AntescofoClient(timeout_seconds=300)` configures individual HTTP connect/read
timeouts. `jobs.wait(timeout_seconds=...)` is a separate waiting budget, not a
server cancellation or a guaranteed hard wall-clock limit for in-flight requests.

## Examples

Run from this repository after installation:

```sh
uv run python examples/analyze.py --audio performance.mp3 --score score.xml --output outputs/result.json
uv run python examples/submit.py --audio performance.mp3 --score score.xml
uv run python examples/resume.py JOB_UUID --output outputs/result.json
uv run python examples/usage.py
```

The first two commands each create a job; do not run both just to retrieve the
same result. `resume.py` never creates a new job. If you installed with pip,
run these commands with `python` instead of `uv run python` in that environment.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, offline tests, and an
optional integration check using your own API access.

## Support And License

Explore demos and integration resources at
[Antescofo Platform](https://platform.antescofo.com/). For API access or integration
questions, contact [research@antescofo.com](mailto:research@antescofo.com).

This Python client is licensed under the [MIT License](LICENSE). API access and
service usage are managed separately through Antescofo Platform. The package does
not include Antescofo's analysis engines or on-device SDKs.

For security concerns, see [SECURITY.md](SECURITY.md).
