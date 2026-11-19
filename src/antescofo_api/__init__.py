"""Antescofo music intelligence API client."""

from ._version import __version__
from .client import AntescofoClient
from .errors import (
    AntescofoError,
    APIError,
    AuthenticationError,
    ConfigurationError,
    JobCanceledError,
    JobFailedError,
    JobTimeoutError,
    NotFoundError,
    ProtocolError,
    QuotaExceededError,
    ResultUnavailableError,
    SubmissionError,
    TransportError,
    UploadError,
)
from .models import Job, JobPage, JobStatus

__all__ = [
    "APIError",
    "AntescofoClient",
    "AntescofoError",
    "AuthenticationError",
    "ConfigurationError",
    "Job",
    "JobCanceledError",
    "JobFailedError",
    "JobPage",
    "JobStatus",
    "JobTimeoutError",
    "NotFoundError",
    "ProtocolError",
    "QuotaExceededError",
    "ResultUnavailableError",
    "SubmissionError",
    "TransportError",
    "UploadError",
    "__version__",
]
