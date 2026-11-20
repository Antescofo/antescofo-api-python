import json
from uuid import UUID

import pytest
import requests

from antescofo_api import (
    AntescofoClient,
    APIError,
    AuthenticationError,
    ConfigurationError,
    Job,
    JobFailedError,
    NotFoundError,
    ProtocolError,
    QuotaExceededError,
    ResultUnavailableError,
    SubmissionError,
    TransportError,
    UploadError,
)
from antescofo_api.client import DEFAULT_API_BASE_URL

from .conftest import (
    API,
    AUDIO_URL,
    JOB_ID,
    JOB_URL,
    KEY,
    OTHER_ID,
    RESULT,
    RESULT_URL,
    SCORE_URL,
    job_payload,
)


def test_analyze_submits_once_and_preserves_full_output(client, inputs, success_flow):
    uploaded = {}

    def capture_upload(role):
        def capture(request, context):
            uploaded[role] = request.body.read()
            return ""

        return capture

    success_flow.put(SCORE_URL, text=capture_upload("score"))
    success_flow.put(AUDIO_URL, text=capture_upload("audio"))
    result = client.performance_analyzer.analyze(**inputs)
    assert result == RESULT
    history = success_flow.request_history
    creates = [request for request in history if request.method == "POST"]
    assert len(creates) == 1
    assert creates[0].json() == {
        "module": "performance_analyzer",
        "score_format": "xml",
        "audio_format": "wav",
    }
    assert "organization_id" not in creates[0].json()
    for request in history:
        if request.hostname == "api.example":
            assert request.headers["X-Api-Key"] == KEY
        else:
            assert "X-Api-Key" not in request.headers
            assert "Authorization" not in request.headers
            assert "Cookie" not in request.headers
            assert request.query.startswith("signature=")
    puts = [request for request in history if request.method == "PUT"]
    assert len(puts) == 2
    assert uploaded["score"] == inputs["score"].read_bytes()
    assert uploaded["audio"] == inputs["audio"].read_bytes()
    assert all(request.headers["Content-Type"] == "application/octet-stream" for request in puts)


def test_submit_returns_safe_handle_and_preserves_api_duration(client, inputs, success_flow):
    job = client.performance_analyzer.submit(**inputs)
    assert job.id == UUID(JOB_ID)
    assert job.status == "pending"
    assert job.upload_urls == {"score": SCORE_URL, "audio": AUDIO_URL}
    assert "signature" not in repr(job)
    assert "upload_urls" not in job.to_dict()
    assert "file_duration" not in success_flow.request_history[0].json()
    assert job.audio_duration_seconds == 91
    assert len(success_flow.request_history) == 3


@pytest.mark.parametrize("method", ["analyze", "submit"])
def test_duration_override_is_not_accepted(client, inputs, requests_mock, method):
    with pytest.raises(TypeError, match="audio_duration_seconds"):
        getattr(client.performance_analyzer, method)(**inputs, audio_duration_seconds=91)
    assert not requests_mock.called


@pytest.mark.parametrize("duration", [None, 0, 42])
def test_submit_never_synthesizes_api_duration(client, inputs, success_flow, duration):
    success_flow.post(
        f"{API}/v1/jobs/",
        status_code=201,
        json=job_payload(
            "pending",
            file_duration=duration,
            upload_urls={"score": SCORE_URL, "audio": AUDIO_URL},
        ),
    )
    job = client.performance_analyzer.submit(**inputs)
    assert job.audio_duration_seconds == duration
    assert "file_duration" not in success_flow.request_history[0].json()


def test_upload_retry_reuses_handle_without_creating(client, inputs, success_flow):
    success_flow.put(AUDIO_URL, [{"status_code": 503}, {"status_code": 200}])
    with pytest.raises(UploadError) as error:
        client.performance_analyzer.submit(**inputs)
    assert error.value.job_id == JOB_ID
    assert "signature" not in str(error.value)
    client.performance_analyzer.upload_inputs(error.value.job, **inputs)
    assert sum(item.method == "POST" for item in success_flow.request_history) == 1


def test_upload_missing_files_preserves_job(client, inputs):
    job = Job(UUID(JOB_ID), "pending", upload_urls={"score": SCORE_URL, "audio": AUDIO_URL})
    inputs["audio"].unlink()
    with pytest.raises(UploadError) as error:
        client.performance_analyzer.upload_inputs(job, **inputs)
    assert error.value.job is job


def test_upload_requires_original_handle(client, inputs):
    with pytest.raises(UploadError):
        client.performance_analyzer.upload_inputs(Job(UUID(JOB_ID), "pending"), **inputs)


@pytest.mark.parametrize("failure", [requests.ConnectionError, requests.Timeout])
def test_creation_failure_never_retries(client, inputs, requests_mock, failure):
    requests_mock.post(f"{API}/v1/jobs/", exc=failure("secret raw request"))
    with pytest.raises(SubmissionError, match="may already exist") as error:
        client.performance_analyzer.submit(**inputs)
    assert requests_mock.call_count == 1
    assert error.value.job_id is None
    assert "secret raw" not in str(error.value)


def test_invalid_wait_options_do_not_create(client, inputs, requests_mock):
    with pytest.raises(ValueError):
        client.performance_analyzer.analyze(**inputs, timeout_seconds=-1)
    assert not requests_mock.called


def test_creation_missing_uploads_retains_id(client, inputs, requests_mock):
    requests_mock.post(f"{API}/v1/jobs/", json=job_payload("pending"), status_code=201)
    with pytest.raises(ProtocolError) as error:
        client.performance_analyzer.submit(**inputs)
    assert error.value.job_id == JOB_ID
    assert requests_mock.call_count == 1


def test_cookie_netrc_and_session_auth_never_reach_storage(
    client,
    inputs,
    success_flow,
    monkeypatch,
    tmp_path,
):
    netrc = tmp_path / ".netrc"
    netrc.write_text("machine storage.example login private password private\n")
    monkeypatch.setenv("NETRC", str(netrc))
    client._transport._session.auth = ("unwanted", "password")
    client._transport._session.headers["Authorization"] = "Bearer unwanted"
    client._transport._session.cookies.set("private", "cookie", domain="storage.example")
    client.performance_analyzer.analyze(**inputs)
    for request in success_flow.request_history:
        assert "Authorization" not in request.headers
        assert "Cookie" not in request.headers
        if request.hostname == "storage.example":
            assert "X-Api-Key" not in request.headers


@pytest.mark.parametrize("target", ["api", "storage"])
def test_redirects_are_not_followed(client, inputs, success_flow, target):
    if target == "api":
        success_flow.get(JOB_URL, status_code=302, headers={"Location": "https://evil.example"})
        with pytest.raises(ProtocolError):
            client.jobs.get(JOB_ID)
    else:
        success_flow.put(SCORE_URL, status_code=307, headers={"Location": "https://evil.example"})
        with pytest.raises(UploadError):
            client.performance_analyzer.submit(**inputs)
    assert not any(request.hostname == "evil.example" for request in success_flow.request_history)


@pytest.mark.parametrize(
    "status,error_class",
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, AuthenticationError),
        (404, NotFoundError),
        (429, QuotaExceededError),
        (500, APIError),
        (503, APIError),
    ],
)
@pytest.mark.parametrize("job_id", [JOB_ID, UUID(JOB_ID)])
def test_api_errors_keep_status_code_body_and_job_id(
    client, requests_mock, status, error_class, job_id
):
    payload = {"code": "test_code", "detail": "Readable server explanation."}
    requests_mock.get(JOB_URL, status_code=status, json=payload)
    with pytest.raises(error_class) as error:
        client.jobs.get(job_id)
    assert error.value.status_code == status
    assert error.value.code == "test_code"
    assert error.value.details == payload
    assert error.value.job_id == JOB_ID
    assert str(error.value) == "Readable server explanation."


def test_api_key_redacted_if_echoed_by_server(client, requests_mock):
    requests_mock.get(JOB_URL, status_code=403, json={"detail": f"Rejected {KEY}"})
    with pytest.raises(AuthenticationError) as error:
        client.jobs.get(JOB_ID)
    assert KEY not in str(error.value)
    assert KEY not in json.dumps(error.value.details)


def test_field_validation_body_is_preserved(client, inputs, requests_mock):
    requests_mock.post(f"{API}/v1/jobs/", status_code=400, json={"module": ["Not entitled."]})
    with pytest.raises(APIError) as error:
        client.performance_analyzer.submit(**inputs)
    assert error.value.details == {"module": ["Not entitled."]}
    assert "Not entitled" in str(error.value)


def test_signed_urls_redacted_from_server_errors(client, requests_mock):
    requests_mock.get(
        JOB_URL,
        json=job_payload(
            "failed",
            error={"message": f"Cannot download {RESULT_URL}"},
        ),
    )
    with pytest.raises(JobFailedError, match="URL REDACTED") as error:
        client.jobs.wait(JOB_ID)
    assert "private-result" not in str(error.value)


def test_html_error_is_not_exposed(client, requests_mock):
    requests_mock.get(JOB_URL, status_code=500, text="<html>private server internals</html>")
    with pytest.raises(APIError, match="HTTP 500") as error:
        client.jobs.get(JOB_ID)
    assert "private" not in str(error.value)


def test_invalid_success_json(client, requests_mock):
    requests_mock.get(JOB_URL, text="not JSON")
    with pytest.raises(ProtocolError, match="valid JSON"):
        client.jobs.get(JOB_ID)


def test_network_error_keeps_id_and_sanitizes_url(client, requests_mock):
    requests_mock.get(JOB_URL, exc=requests.ConnectionError(f"request headers {KEY}"))
    with pytest.raises(TransportError) as error:
        client.jobs.get(JOB_ID)
    assert error.value.job_id == JOB_ID
    assert KEY not in str(error.value)


@pytest.mark.parametrize("method", ["get", "wait", "get_result"])
@pytest.mark.parametrize("job_id", [JOB_ID, UUID(JOB_ID), JOB_ID.upper(), UUID(JOB_ID).hex])
def test_job_methods_accept_uuid_or_string(client, success_flow, method, job_id):
    result = getattr(client.jobs, method)(job_id)
    if method == "get_result":
        assert result == RESULT
    else:
        assert isinstance(result.id, UUID)
        assert result.id == UUID(JOB_ID)
    assert success_flow.request_history[0].url == JOB_URL
    assert all(request.method == "GET" for request in success_flow.request_history)


@pytest.mark.parametrize("method", ["get", "wait", "get_result"])
@pytest.mark.parametrize("bad_id", ["../usage", "", "not-a-uuid", None, 42, b"invalid"])
def test_invalid_ids_make_no_request(client, requests_mock, method, bad_id):
    with pytest.raises(ValueError):
        getattr(client.jobs, method)(bad_id)
    assert not requests_mock.called


@pytest.mark.parametrize("job_id", [JOB_ID, UUID(JOB_ID)])
def test_mismatched_job_id_rejected(client, requests_mock, job_id):
    requests_mock.get(JOB_URL, json=job_payload(uuid=OTHER_ID))
    with pytest.raises(ProtocolError, match="different") as error:
        client.jobs.get(job_id)
    assert error.value.job_id == JOB_ID


def test_list_uses_filters_and_does_not_follow_next(client, requests_mock):
    requests_mock.get(
        f"{API}/v1/jobs/",
        json={
            "count": 42,
            "next": "https://untrusted.example",
            "previous": None,
            "results": [job_payload()],
        },
    )
    page = client.jobs.list(
        limit=10,
        offset=20,
        module="performance_analyzer",
        status="succeeded",
        created_from="2026-11-01T00:00:00Z",
        created_to="2026-12-01T00:00:00Z",
    )
    assert page.count == 42
    assert page.results[0].id == UUID(JOB_ID)
    assert page.next == "https://untrusted.example"
    assert requests_mock.call_count == 1
    assert requests_mock.last_request.qs["offset"] == ["20"]
    assert requests_mock.last_request.qs["module"] == ["performance_analyzer"]


@pytest.mark.parametrize(
    "kwargs",
    [{"limit": 0}, {"offset": -1}, {"status": "unknown"}, {"limit": True}, {"offset": 1.5}],
)
def test_list_invalid_filters(client, requests_mock, kwargs):
    with pytest.raises(ValueError):
        client.jobs.list(**kwargs)
    assert not requests_mock.called


@pytest.mark.parametrize(
    "payload",
    [[], {"results": []}, {"count": -1, "results": []}, {"count": 1, "results": [], "next": 3}],
)
def test_invalid_list_schema(client, requests_mock, payload):
    requests_mock.get(f"{API}/v1/jobs/", json=payload)
    with pytest.raises(ProtocolError):
        client.jobs.list()


def test_usage_organization_totals(client, requests_mock):
    usage = {
        "account": {"type": "organization", "name": "Test organization", "id": 1},
        "jobs": 2,
        "total_file_seconds": 91,
        "monthly_jobs": {},
    }
    requests_mock.get(f"{API}/v1/usage/", json=usage)
    assert client.usage.get() == usage
    assert "organization_id" not in requests_mock.last_request.qs


def test_invalid_usage_schema(client, requests_mock):
    requests_mock.get(f"{API}/v1/usage/", json={"jobs": 0})
    with pytest.raises(ProtocolError):
        client.usage.get()


def test_result_requires_success_without_waiting(client, success_flow):
    success_flow.get(JOB_URL, json=job_payload("running"))
    with pytest.raises(ResultUnavailableError) as error:
        client.jobs.get_result(JOB_ID)
    assert error.value.job_id == JOB_ID
    assert success_flow.call_count == 1


@pytest.mark.parametrize(
    "outputs,error_class",
    [
        ([], ResultUnavailableError),
        ([{"role": "other"}], ResultUnavailableError),
        ([{"role": "analysis", "filename": "result.json", "url": 3}], ProtocolError),
        ([{"role": "analysis", "filename": "result.json", "url": RESULT_URL}] * 2, ProtocolError),
    ],
)
def test_missing_or_invalid_output(client, success_flow, outputs, error_class):
    success_flow.get(f"{JOB_URL}files/", json={"outputs": outputs})
    with pytest.raises(error_class) as error:
        client.jobs.get_result(JOB_ID)
    assert error.value.job_id == JOB_ID


def test_invalid_files_response(client, success_flow):
    success_flow.get(f"{JOB_URL}files/", json=[])
    with pytest.raises(ProtocolError):
        client.jobs.get_result(JOB_ID)


def test_unsafe_output_url_is_rejected(client, success_flow):
    success_flow.get(
        f"{JOB_URL}files/",
        json={
            "outputs": [
                {"role": "analysis", "filename": "result.json", "url": "http://evil.example"},
            ]
        },
    )
    with pytest.raises(ProtocolError, match="unsafe"):
        client.jobs.get_result(JOB_ID)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"alignment_interop": [], "assessment": []},
        {"alignment_interop": [], "assessment": {"metrics": 3}},
    ],
)
def test_invalid_result_schema(client, success_flow, payload):
    success_flow.get(RESULT_URL, json=payload)
    with pytest.raises(ProtocolError):
        client.jobs.get_result(JOB_ID)


@pytest.mark.parametrize(
    "payload",
    [
        {"alignment_interop": []},
        {"alignment_interop": [], "assessment": None},
        {"alignment_interop": [], "assessment": {"overall": None, "metrics": []}},
    ],
)
def test_optional_assessment(client, success_flow, payload):
    success_flow.get(RESULT_URL, json=payload)
    assert client.jobs.get_result(JOB_ID) == payload


def test_expired_result_url_gets_refreshed_on_retry(client, success_flow):
    success_flow.get(RESULT_URL, [{"status_code": 403}, {"json": RESULT}])
    with pytest.raises(TransportError) as error:
        client.jobs.get_result(JOB_ID)
    assert error.value.job_id == JOB_ID
    assert "private-result" not in str(error.value)
    assert client.jobs.get_result(JOB_ID) == RESULT
    assert sum(request.url == f"{JOB_URL}files/" for request in success_flow.request_history) == 2


def test_closed_client_rejects_new_requests(client, requests_mock):
    client.close()
    with pytest.raises(ConfigurationError, match="closed"):
        client.jobs.get(JOB_ID)
    assert not requests_mock.called


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("ANTESCOFO_API_KEY", KEY)
    monkeypatch.setenv("ANTESCOFO_API_BASE_URL", API + "/")
    with AntescofoClient() as value:
        assert value.base_url == API
        assert KEY not in repr(value)


def test_api_key_only_selects_the_public_production_api(monkeypatch, requests_mock):
    monkeypatch.delenv("ANTESCOFO_API_BASE_URL", raising=False)
    assert DEFAULT_API_BASE_URL == "https://api.platform.metronaut.app"
    with AntescofoClient(KEY) as value:
        assert value.base_url == DEFAULT_API_BASE_URL
    assert not requests_mock.called


def test_default_client_routes_requests_with_api_key_without_environment_failover(
    monkeypatch, requests_mock
):
    monkeypatch.delenv("ANTESCOFO_API_BASE_URL", raising=False)
    monkeypatch.setenv("ANTESCOFO_API_KEY", KEY)
    endpoint = f"{DEFAULT_API_BASE_URL}/v1/usage/"
    requests_mock.get(endpoint, status_code=403, json={"detail": "Invalid API key."})
    with AntescofoClient() as value, pytest.raises(AuthenticationError):
        value.usage.get()
    assert requests_mock.call_count == 1
    assert requests_mock.last_request.url == endpoint
    assert requests_mock.last_request.headers["X-Api-Key"] == KEY


@pytest.mark.parametrize("origin", ["https://wrong.example", "", "   "])
def test_explicit_api_origin_overrides_environment(monkeypatch, origin):
    monkeypatch.setenv("ANTESCOFO_API_BASE_URL", origin)
    with AntescofoClient(KEY, base_url=API) as value:
        assert value.base_url == API


@pytest.mark.parametrize("origin", ["", "   "])
def test_empty_api_origin_fails_before_network(monkeypatch, requests_mock, origin):
    monkeypatch.setenv("ANTESCOFO_API_BASE_URL", origin)
    with pytest.raises(ConfigurationError, match="ANTESCOFO_API_BASE_URL"):
        AntescofoClient(KEY)
    with pytest.raises(ConfigurationError, match="ANTESCOFO_API_BASE_URL"):
        AntescofoClient(KEY, base_url=origin)
    assert not requests_mock.called


@pytest.mark.parametrize("key", ["", "bad\nkey", "bad key"])
def test_invalid_credentials(key):
    with pytest.raises(ConfigurationError):
        AntescofoClient(key)


def test_missing_environment_key(monkeypatch):
    monkeypatch.delenv("ANTESCOFO_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        AntescofoClient()


@pytest.mark.parametrize(
    "origin",
    [
        "http://api.example",
        "https://user:password@api.example",
        "https://api.example/path",
        "https://api.example?key=secret",
        "https://api.example#fragment",
        "not-a-url",
        "https://api.example:invalid",
        "https://api.example:0",
    ],
)
def test_unsafe_origins(origin):
    with pytest.raises(ConfigurationError):
        AntescofoClient(KEY, base_url=origin)


@pytest.mark.parametrize(
    "origin", ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"]
)
def test_loopback_http_development(origin):
    with AntescofoClient(KEY, base_url=origin) as value:
        assert value.base_url == origin
