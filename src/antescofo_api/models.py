"""Stable job handles; analysis dictionaries preserve the engine's full schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast
from uuid import UUID

from .errors import ProtocolError

JobStatus = Literal["pending", "ready", "running", "succeeded", "failed", "canceled"]
JOB_STATUSES = {"pending", "ready", "running", "succeeded", "failed", "canceled"}


@dataclass(frozen=True)
class Job:
    """A job snapshot. Upload URLs are temporary credentials, omitted from repr.

    id is the API's uuid as a UUID object. upload_urls is present only on a
    creation handle; status retrieval cannot recreate expired or lost upload URLs.
    audio_duration_seconds is the API's file_duration, if available; the client
    does not measure it or substitute a local estimate.
    """

    id: UUID
    status: JobStatus
    module: str | None = None
    audio_duration_seconds: int | None = None
    created_at: str | None = None
    finished_at: str | None = None
    error: dict[str, Any] | None = field(default=None, repr=False)
    upload_urls: dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Export a snapshot with a UUID string and no signed URLs for recovery records."""
        return {
            "uuid": str(self.id),
            "status": self.status,
            "module": self.module,
            "file_duration": self.audio_duration_seconds,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


@dataclass(frozen=True)
class JobPage:
    """One API page; pagination URLs are metadata, never followed automatically."""

    count: int
    results: tuple[Job, ...]
    next: str | None = None
    previous: str | None = None


def parse_job(payload: Any, *, job_id: str | None = None) -> Job:
    if not isinstance(payload, dict):
        raise ProtocolError("Expected a job object.", job_id=job_id)
    try:
        identifier = normalize_job_id(payload["uuid"])
    except (KeyError, TypeError, ValueError):
        raise ProtocolError("The API did not return a valid job UUID.", job_id=job_id) from None
    if job_id is not None and identifier != job_id:
        raise ProtocolError("The API returned a different job UUID.", job_id=job_id)
    status = payload.get("status")
    if not isinstance(status, str) or status not in JOB_STATUSES:
        raise ProtocolError("The API returned an unknown job status.", job_id=identifier)
    error = payload.get("error")
    if error is not None and not isinstance(error, dict):
        raise ProtocolError("The API returned an invalid job error.", job_id=identifier)
    urls = payload.get("upload_urls", {})
    if not isinstance(urls, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in urls.items()
    ):
        raise ProtocolError("The API returned invalid upload URLs.", job_id=identifier)
    duration = payload.get("file_duration")
    if duration is not None and (type(duration) is not int or duration < 0):
        raise ProtocolError("The API returned an invalid audio duration.", job_id=identifier)
    for name in ("module", "created_at", "finished_at"):
        if payload.get(name) is not None and not isinstance(payload[name], str):
            raise ProtocolError(f"The API returned an invalid {name}.", job_id=identifier)
    return Job(
        id=UUID(identifier),
        status=cast(JobStatus, status),
        module=payload.get("module"),
        audio_duration_seconds=duration,
        created_at=payload.get("created_at"),
        finished_at=payload.get("finished_at"),
        error=error,
        upload_urls=dict(urls),
    )


def normalize_job_id(value: str | UUID) -> str:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise ValueError("job_id must be a UUID or UUID string.")
    return str(UUID(value))
