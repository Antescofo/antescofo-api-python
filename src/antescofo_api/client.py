"""Synchronous client for the create / upload / poll / download contract."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from ._inputs import positive_seconds, prepare_inputs, validate_file
from ._transport import Transport
from .errors import (
    ConfigurationError,
    JobCanceledError,
    JobFailedError,
    JobTimeoutError,
    ProtocolError,
    ResultUnavailableError,
    TransportError,
    UploadError,
)
from .models import JOB_STATUSES, Job, JobPage, JobStatus, normalize_job_id, parse_job

DEFAULT_API_BASE_URL = "https://api.platform.metronaut.app"


class AntescofoClient:
    """Organization member-key client, not a website-login or compute engine.

    Explicit arguments override ANTESCOFO_API_KEY / ANTESCOFO_API_BASE_URL.
    Only the API key is required; the production API is selected automatically.
    base_url or ANTESCOFO_API_BASE_URL optionally selects another API environment.
    A configured but empty/invalid origin is rejected, never silently replaced.
    timeout_seconds bounds individual HTTP connect/read operations, not analysis.
    Use as a context manager. Instances are synchronous and not thread-safe.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("ANTESCOFO_API_KEY", "")
        if (
            not isinstance(key, str)
            or not key
            or any(not "!" <= character <= "~" for character in key)
        ):
            raise ConfigurationError("Set ANTESCOFO_API_KEY or provide your full member API key.")
        origin = (
            base_url
            if base_url is not None
            else os.environ.get("ANTESCOFO_API_BASE_URL", DEFAULT_API_BASE_URL)
        )
        if not isinstance(origin, str) or not origin.strip():
            raise ConfigurationError(
                "ANTESCOFO_API_BASE_URL / base_url must be a nonempty API origin when set. "
                "Omit the override entirely to use the default Antescofo API."
            )
        self._transport = Transport(
            key, origin, positive_seconds(timeout_seconds, "timeout_seconds")
        )
        self.base_url = self._transport.base_url
        self.jobs = Jobs(self._transport)
        self.usage = Usage(self._transport)
        self.performance_analyzer = PerformanceAnalyzer(self._transport, self.jobs)

    def close(self) -> None:
        """Release HTTP connections. The server's existing jobs continue."""
        self._transport.close()

    def __enter__(self) -> AntescofoClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class PerformanceAnalyzer:
    """Submit piano audio plus MusicXML without running any analysis locally."""

    def __init__(self, transport: Transport, jobs: Jobs) -> None:
        self._transport = transport
        self._jobs = jobs

    def analyze(
        self,
        *,
        audio: str | Path,
        score: str | Path,
        timeout_seconds: float = 1800,
        poll_interval_seconds: float = 3,
    ) -> dict[str, Any]:
        """Submit exactly once, wait, then return the unmodified analysis JSON.

        timeout_seconds applies to waiting after uploads. Any recoverable error
        after creation includes job_id; do not call analyze again to resume it.
        """
        positive_seconds(timeout_seconds, "timeout_seconds")
        positive_seconds(poll_interval_seconds, "poll_interval_seconds")
        job = self.submit(audio=audio, score=score)
        self._jobs.wait(
            job.id, timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds
        )
        return self._jobs.get_result(job.id)

    def submit(
        self,
        *,
        audio: str | Path,
        score: str | Path,
    ) -> Job:
        """Validate locally, create one job, upload originals, and return its handle.

        Audio duration is not supplied by the client. Decoding and measurement
        belong to the service after upload, not to client-supplied metadata.
        Creation is never retried automatically: each accepted POST consumes quota.
        """
        inputs = prepare_inputs(audio, score)
        payload = self._transport.api(
            "POST",
            "jobs/",
            body={
                "module": "performance_analyzer",
                "score_format": "xml",
                "audio_format": inputs.audio_format,
            },
        )
        job = replace(
            parse_job(payload),
            module="performance_analyzer",
        )
        if not job.upload_urls.get("audio") or not job.upload_urls.get("score"):
            raise ProtocolError(
                "Creation did not return both upload URLs. Do not resubmit.", job_id=job.id
            )
        self.upload_inputs(job, audio=inputs.audio, score=inputs.score)
        return job

    def upload_inputs(self, job: Job, *, audio: str | Path, score: str | Path) -> None:
        """Retry original input PUTs using a creation handle, never a new POST.

        Reuse the same original files. Signed upload URLs expire (currently one
        hour); GET job details does not refresh them. Server processing starts
        automatically. This method does not cancel already-started processing.
        """
        normalize_job_id(job.id)
        try:
            audio_path = validate_file(audio, {".mp3", ".wav"}, "Audio")
            score_path = validate_file(score, {".xml", ".musicxml"}, "Score")
            if not job.upload_urls.get("score") or not job.upload_urls.get("audio"):
                raise ValueError("Use the original creation handle containing upload URLs.")
            for role, path in (("score", score_path), ("audio", audio_path)):
                with path.open("rb") as source:
                    self._transport.upload(job.upload_urls[role], source, job_id=job.id)
        except (OSError, ValueError, TransportError, ConfigurationError, ProtocolError) as error:
            raise UploadError(
                f"Input transfer failed: {error} Preserve this handle and retry upload_inputs with "
                "the same original files while its signed URLs are valid.",
                job=job,
            ) from None


class Jobs:
    """Retrieve, wait for, and recover existing jobs without consuming new quota."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(self, job_id: str) -> Job:
        identifier = normalize_job_id(job_id)
        return self._get(identifier)

    def wait(
        self,
        job_id: str,
        *,
        timeout_seconds: float = 1800,
        poll_interval_seconds: float = 3,
    ) -> Job:
        """Poll sequentially until success, failure, cancellation, or timeout.

        Poll interval starts after each response. Timeout does not cancel server
        processing. In-flight HTTP calls use the remaining wait budget for their
        individual connect/read timeouts, not a guaranteed wall-clock deadline.
        """
        identifier = normalize_job_id(job_id)
        deadline = time.monotonic() + positive_seconds(timeout_seconds, "timeout_seconds")
        interval = positive_seconds(poll_interval_seconds, "poll_interval_seconds")
        last_job = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobTimeoutError(job_id=identifier, last_job=last_job)
            last_job = self._get(identifier, timeout_seconds=remaining)
            raise_terminal_error(last_job)
            if last_job.status == "succeeded":
                return last_job
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobTimeoutError(job_id=identifier, last_job=last_job)
            time.sleep(min(interval, remaining))

    def get_result(self, job_id: str) -> dict[str, Any]:
        """Download a successful job's JSON; this method does not wait for compute.

        Each call obtains a fresh signed URL. Missing/wrong/extra notes, velocity,
        onset deviations, assessments, and future fields are preserved as returned.
        """
        job = self.get(job_id)
        raise_terminal_error(job)
        if job.status != "succeeded":
            raise ResultUnavailableError(
                "The job has not succeeded yet. Call jobs.wait first.", job_id=job.id
            )
        files = self._transport.api("GET", f"jobs/{job.id}/files/", job_id=job.id)
        if not isinstance(files, dict) or not isinstance(files.get("outputs"), list):
            raise ProtocolError("The files response is invalid.", job_id=job.id)
        matches = [
            output
            for output in files["outputs"]
            if isinstance(output, dict)
            and output.get("role") == "analysis"
            and output.get("filename") == "result.json"
        ]
        if not matches:
            raise ResultUnavailableError(
                "Analysis output is not available. Retry this same job.", job_id=job.id
            )
        if len(matches) != 1 or not isinstance(matches[0].get("url"), str):
            raise ProtocolError("The analysis output is ambiguous or invalid.", job_id=job.id)
        try:
            result = self._transport.download(matches[0]["url"], job_id=job.id)
        except ConfigurationError:
            raise ProtocolError("The API returned an unsafe result URL.", job_id=job.id) from None
        if not isinstance(result, dict) or not isinstance(result.get("alignment_interop"), list):
            raise ProtocolError(
                "Analysis JSON must contain alignment_interop events.", job_id=job.id
            )
        assessment = result.get("assessment")
        if assessment is not None and (
            not isinstance(assessment, dict)
            or not isinstance(assessment.get("metrics"), list)
            or (
                assessment.get("overall") is not None
                and not isinstance(assessment["overall"], (float, int))
            )
        ):
            raise ProtocolError("Analysis assessment has an unexpected format.", job_id=job.id)
        return cast(dict[str, Any], result)

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        module: str | None = None,
        status: JobStatus | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
    ) -> JobPage:
        """Return one page. Creation date filters are ISO timestamps, upper bound exclusive."""
        if type(limit) is not int or limit <= 0 or type(offset) is not int or offset < 0:
            raise ValueError("limit must be a positive integer and offset a nonnegative integer.")
        if status is not None and status not in JOB_STATUSES:
            raise ValueError("Unknown job status filter.")
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        params.update(
            {
                key: value
                for key, value in {
                    "module": module,
                    "status": status,
                    "created_from": created_from,
                    "created_to": created_to,
                }.items()
                if value is not None
            }
        )
        data = self._transport.api("GET", "jobs/", params=params)
        if (
            not isinstance(data, dict)
            or type(data.get("count")) is not int
            or data["count"] < 0
            or not isinstance(data.get("results"), list)
            or any(
                data.get(key) is not None and not isinstance(data[key], str)
                for key in ("next", "previous")
            )
        ):
            raise ProtocolError("Expected a paginated jobs response.")
        return JobPage(
            count=data["count"],
            results=tuple(parse_job(item) for item in data["results"]),
            next=data.get("next"),
            previous=data.get("previous"),
        )

    def _get(self, identifier: str, *, timeout_seconds: float | None = None) -> Job:
        payload = self._transport.api(
            "GET", f"jobs/{identifier}/", job_id=identifier, timeout_seconds=timeout_seconds
        )
        return parse_job(payload, job_id=identifier)


class Usage:
    """Organization usage reported by the API, aggregated across its members."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(self) -> dict[str, Any]:
        data = self._transport.api("GET", "usage/")
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("account"), dict)
            or type(data.get("jobs")) is not int
            or not isinstance(data.get("total_file_seconds"), (int, float))
        ):
            raise ProtocolError("Expected an account usage object.")
        return cast(dict[str, Any], data)


def raise_terminal_error(job: Job) -> None:
    if job.status == "canceled":
        raise JobCanceledError("The job was canceled or its upload reservation expired.", job=job)
    if job.status == "failed":
        message = job.error.get("message") if job.error else None
        raise JobFailedError(message if isinstance(message, str) else "Analysis failed.", job=job)
