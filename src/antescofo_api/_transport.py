"""Credential-isolated HTTP transport. Creation POSTs are never retried."""

from __future__ import annotations

import ipaddress
import re
from contextlib import suppress
from typing import Any, BinaryIO
from urllib.parse import urlsplit

import requests

from ._version import __version__
from .errors import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    ProtocolError,
    QuotaExceededError,
    SubmissionError,
    TransportError,
)


class Transport:
    def __init__(self, api_key: str, base_url: str, timeout_seconds: float) -> None:
        self.base_url = validate_url(base_url, origin_only=True).rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._session = requests.Session()
        self._closed = False

    def close(self) -> None:
        self._session.close()
        self._closed = True

    def api(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        job_id: str | None = None,
        timeout_seconds: float | None = None,
    ) -> Any:
        response = self._send(
            method,
            self.base_url + "/v1/" + path,
            headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
            body=body,
            params=params,
            job_id=job_id,
            creating=method == "POST",
            timeout_seconds=timeout_seconds,
        )
        with response:
            data = self._json(response, job_id)
            if not 200 <= response.status_code < 300:
                self._api_error(response.status_code, data, job_id)
            data = self._redact(data)
            if isinstance(data, dict) and data.get("error") is not None:
                data["error"] = self._redact(data["error"], hide_urls=True)
            return data

    def upload(self, url: str, source: BinaryIO, *, job_id: str) -> None:
        response = self._send(
            "PUT",
            url,
            headers={"Content-Type": "application/octet-stream"},
            data=source,
            job_id=job_id,
        )
        with response:
            if not 200 <= response.status_code < 300:
                raise TransportError(
                    f"Storage upload returned HTTP {response.status_code}. "
                    "Retry the same job while its signed URLs are valid.",
                    job_id=job_id,
                )

    def download(self, url: str, *, job_id: str) -> Any:
        response = self._send("GET", url, headers={}, job_id=job_id)
        with response:
            if not 200 <= response.status_code < 300:
                raise TransportError(
                    f"Storage download returned HTTP {response.status_code}. "
                    "Call get_result again to obtain a fresh URL.",
                    job_id=job_id,
                )
            return self._redact(self._json(response, job_id))

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: BinaryIO | None = None,
        job_id: str | None = None,
        creating: bool = False,
        timeout_seconds: float | None = None,
    ) -> requests.Response:
        if self._closed:
            raise ConfigurationError("This client is closed.")
        validate_url(url)
        # Preparing outside Session deliberately excludes cookie jars, default auth,
        # and .netrc credentials. Environment proxy/CA settings still work below.
        prepared = requests.Request(
            method,
            url,
            headers={"User-Agent": f"antescofo-api/{__version__}", **headers},
            json=body,
            params=params,
            data=data,
        ).prepare()
        settings = self._session.merge_environment_settings(
            prepared.url or url, {}, None, None, None
        )
        timeout = min(self._timeout, timeout_seconds) if timeout_seconds else self._timeout
        try:
            response = self._session.send(
                prepared,
                timeout=(min(20.0, timeout), timeout),
                allow_redirects=False,
                **settings,
            )
        except requests.RequestException:
            if creating:
                raise SubmissionError(
                    "The creation response could not be received; a job may already exist. "
                    "Inspect jobs.list() before submitting again."
                ) from None
            raise TransportError(
                "The HTTP request timed out or could not connect.", job_id=job_id
            ) from None
        if 300 <= response.status_code < 400:
            response.close()
            raise ProtocolError(
                "HTTP redirects are not followed. Verify the API or storage URL.", job_id=job_id
            )
        return response

    def _json(self, response: requests.Response, job_id: str | None) -> Any:
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            if not 200 <= response.status_code < 300:
                self._api_error(response.status_code, None, job_id)
            raise ProtocolError("The response was not valid JSON.", job_id=job_id) from None

    def _redact(self, data: Any, *, hide_urls: bool = False) -> Any:
        if isinstance(data, str):
            data = data.replace(self._api_key, "[REDACTED]")
            return re.sub(r"https?://[^\s<>\"']+", "[URL REDACTED]", data) if hide_urls else data
        if isinstance(data, list):
            return [self._redact(value, hide_urls=hide_urls) for value in data]
        if isinstance(data, dict):
            return {key: self._redact(value, hide_urls=hide_urls) for key, value in data.items()}
        return data

    def _api_error(self, status: int, data: Any, job_id: str | None) -> None:
        data = self._redact(data, hide_urls=True)
        code = data.get("code") if isinstance(data, dict) else None
        message = data.get("detail") or data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, str):
            if isinstance(data, dict):
                message = "; ".join(f"{name}: {value}" for name, value in data.items())[:2000]
            elif isinstance(data, str):
                message = data[:2000]
            if not message:
                message = f"Antescofo API returned HTTP {status}."
        error_type = {
            401: AuthenticationError,
            403: AuthenticationError,
            404: NotFoundError,
            429: QuotaExceededError,
        }.get(status, APIError)
        raise error_type(
            message,
            status_code=status,
            code=code if isinstance(code, str) else None,
            details=data,
            job_id=job_id,
        )


def validate_url(url: str, *, origin_only: bool = False) -> str:
    """Allow HTTPS origins, with HTTP permitted only for loopback development."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
        loopback = host == "localhost"
        if host and not loopback:
            with suppress(ValueError):
                loopback = ipaddress.ip_address(host).is_loopback
        valid_scheme = parsed.scheme == "https" or (parsed.scheme == "http" and loopback)
        if (
            not host
            or not valid_scheme
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (port is not None and port < 1)
            or (origin_only and (parsed.path not in {"", "/"} or parsed.query))
        ):
            raise ValueError
    except (TypeError, ValueError):
        raise ConfigurationError(
            "Use an HTTPS URL without embedded credentials; base_url must be an origin. "
            "HTTP is permitted only on localhost or loopback addresses."
        ) from None
    return url
