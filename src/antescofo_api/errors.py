"""Public exceptions. Messages never include credentials or signed storage URLs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Job


class AntescofoError(Exception):
    """Base error; job_id identifies an existing job that can be recovered."""

    def __init__(self, message: str, *, job_id: str | None = None) -> None:
        super().__init__(message)
        self.job_id = job_id


class ConfigurationError(AntescofoError, ValueError):
    """Missing credentials or invalid client configuration."""


class APIError(AntescofoError):
    """An API HTTP failure; details preserves the redacted JSON error body."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        details: Any = None,
        job_id: str | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id)
        self.status_code = status_code
        self.code = code
        self.details = details


class AuthenticationError(APIError):
    """The member API key was rejected or access is forbidden (401/403)."""


class QuotaExceededError(APIError):
    """Admission/rate limit reached (429); do not blindly resubmit."""


class NotFoundError(APIError):
    """The job does not exist or is not visible to this API key (404)."""


class TransportError(AntescofoError):
    """An HTTP connection/timeout failure, without a raw request or secret URL."""


class SubmissionError(TransportError):
    """Creation outcome is unknown. Inspect jobs.list() before submitting again."""


class ProtocolError(AntescofoError):
    """The API or analysis returned an unexpected schema or a redirect."""


class UploadError(AntescofoError):
    """Upload failed after creation; retry upload_inputs with the same Job handle.

    job may contain signed upload URLs. Do not log its upload_urls or persist
    them publicly. The handle's normal representation omits those URLs.
    """

    def __init__(self, message: str, *, job: Job) -> None:
        super().__init__(message, job_id=job.id)
        self.job = job


class ResultUnavailableError(AntescofoError):
    """The job is not successful yet, or its analysis output is not available."""


class JobFailedError(AntescofoError):
    """Analysis failed. job retains its status and server error details."""

    def __init__(self, message: str, *, job: Job) -> None:
        super().__init__(message, job_id=job.id)
        self.job = job


class JobCanceledError(JobFailedError):
    """The job was canceled, including expired pending uploads."""


class JobTimeoutError(AntescofoError):
    """Waiting timed out; the server job is not canceled. Resume the same ID."""

    def __init__(self, *, job_id: str, last_job: Job | None = None) -> None:
        super().__init__(
            "Waiting timed out. Resume this job; server processing is not canceled.", job_id=job_id
        )
        self.last_job = last_job
