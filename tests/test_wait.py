import pytest

from antescofo_api import JobCanceledError, JobFailedError, JobTimeoutError, ProtocolError

from .conftest import JOB_ID, JOB_URL, job_payload


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0
        sleeps = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    value = Clock()
    monkeypatch.setattr("antescofo_api.client.time.monotonic", value.monotonic)
    monkeypatch.setattr("antescofo_api.client.time.sleep", value.sleep)
    return value


def test_polls_after_responses_every_three_seconds(client, requests_mock, clock):
    requests_mock.get(
        JOB_URL,
        [{"json": job_payload(status)} for status in ["pending", "ready", "running", "succeeded"]],
    )
    assert client.jobs.wait(JOB_ID).status == "succeeded"
    assert clock.sleeps == [3, 3, 3]
    assert requests_mock.call_count == 4


@pytest.mark.parametrize(
    "status,kind", [("failed", JobFailedError), ("canceled", JobCanceledError)]
)
def test_terminal_failures_stop_polling(client, requests_mock, clock, status, kind):
    requests_mock.get(
        JOB_URL, json=job_payload(status, error={"message": "No detected observations."})
    )
    with pytest.raises(kind) as error:
        client.jobs.wait(JOB_ID)
    assert error.value.job_id == JOB_ID
    assert error.value.job.status == status
    assert requests_mock.call_count == 1
    assert clock.sleeps == []
    if status == "failed":
        assert str(error.value) == "No detected observations."


def test_generic_failed_message(client, requests_mock):
    requests_mock.get(JOB_URL, json=job_payload("failed"))
    with pytest.raises(JobFailedError, match="Analysis failed"):
        client.jobs.get_result(JOB_ID)


def test_timeout_preserves_id_and_can_resume_without_post(client, requests_mock, clock):
    requests_mock.get(JOB_URL, json=job_payload("running"))
    with pytest.raises(JobTimeoutError) as error:
        client.jobs.wait(JOB_ID, timeout_seconds=5)
    assert error.value.job_id == JOB_ID
    assert error.value.last_job.status == "running"
    assert clock.sleeps == [3, 2]
    assert all(request.method == "GET" for request in requests_mock.request_history)
    requests_mock.get(JOB_URL, json=job_payload("succeeded"))
    assert client.jobs.wait(JOB_ID).status == "succeeded"


def test_slow_poll_uses_remaining_budget(client, requests_mock, clock):
    def slow_response(request, context):
        clock.now += 6
        return job_payload("running")

    requests_mock.get(JOB_URL, json=slow_response)
    with pytest.raises(JobTimeoutError):
        client.jobs.wait(JOB_ID, timeout_seconds=5)
    assert clock.sleeps == []
    assert requests_mock.call_count == 1


def test_unknown_status_fails_immediately(client, requests_mock, clock):
    requests_mock.get(JOB_URL, json=job_payload("surprise"))
    with pytest.raises(ProtocolError):
        client.jobs.wait(JOB_ID)
    assert clock.sleeps == []


@pytest.mark.parametrize("kwargs", [{"timeout_seconds": 0}, {"poll_interval_seconds": -1}])
def test_invalid_wait_options(client, requests_mock, kwargs):
    with pytest.raises(ValueError):
        client.jobs.wait(JOB_ID, **kwargs)
    assert not requests_mock.called
