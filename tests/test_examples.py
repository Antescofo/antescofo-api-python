import json
import sys

import pytest

from antescofo_api import AntescofoClient
from examples import analyze, resume, smoke_test, submit, usage

from .conftest import API, JOB_ID, KEY


def configure(monkeypatch, requests_mock):
    monkeypatch.setenv("ANTESCOFO_API_KEY", KEY)
    monkeypatch.setenv("ANTESCOFO_API_BASE_URL", API)
    requests_mock.get(
        f"{API}/v1/jobs/",
        json={
            "count": 1,
            "next": None,
            "previous": None,
            "results": [],
        },
    )
    requests_mock.get(
        f"{API}/v1/usage/",
        [
            {
                "json": {
                    "account": {"type": "organization", "id": 1},
                    "jobs": 2,
                    "total_file_seconds": 91,
                },
            },
            {
                "json": {
                    "account": {"type": "organization", "id": 1},
                    "jobs": 3,
                    "total_file_seconds": 93,
                },
            },
        ],
    )


def test_analyze_example_saves_result(monkeypatch, tmp_path, inputs, success_flow):
    configure(monkeypatch, success_flow)
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze.py",
            "--audio",
            str(inputs["audio"]),
            "--score",
            str(inputs["score"]),
            "--output",
            str(output),
        ],
    )
    analyze.main()
    assert json.loads(output.read_text())["assessment"]["overall"] == 85.5


def test_submit_example_prints_recovery_id(monkeypatch, capsys, inputs, success_flow):
    configure(monkeypatch, success_flow)
    monkeypatch.setattr(
        sys, "argv", ["submit.py", "--audio", str(inputs["audio"]), "--score", str(inputs["score"])]
    )
    submit.main()
    assert JOB_ID in capsys.readouterr().out
    assert success_flow.call_count == 3


def test_resume_example_never_submits(monkeypatch, tmp_path, success_flow):
    configure(monkeypatch, success_flow)
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["resume.py", JOB_ID, "--output", str(output)])
    resume.main()
    assert output.exists()
    assert all(request.method == "GET" for request in success_flow.request_history)


def test_usage_example_never_submits(monkeypatch, success_flow):
    configure(monkeypatch, success_flow)
    usage.main()
    assert all(request.method == "GET" for request in success_flow.request_history)


@pytest.mark.parametrize("create", [True, False])
def test_smoke_report_is_private_and_recoverable(
    monkeypatch,
    tmp_path,
    inputs,
    success_flow,
    create,
):
    configure(monkeypatch, success_flow)
    output = tmp_path / "report"
    argv = [
        "smoke_test.py",
        "--base-url",
        API,
        "--audio",
        str(inputs["audio"]),
        "--score",
        str(inputs["score"]),
        "--output-dir",
        str(output),
    ]
    argv += ["--create-job"] if create else ["--resume-job-id", JOB_ID]
    monkeypatch.setattr(sys, "argv", argv)
    smoke_test.main()
    report = json.loads((output / "report.json").read_text())
    assert report["job"]["uuid"] == JOB_ID
    assert report["job"]["status"] == "succeeded"
    assert KEY not in json.dumps(report)
    assert "signature" not in json.dumps(report)
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "report.json").stat().st_mode & 0o777 == 0o600
    assert (output / "result.json").exists()
    assert sum(request.method == "POST" for request in success_flow.request_history) == int(create)


def test_smoke_report_writer_works_before_network(monkeypatch, tmp_path, inputs):
    def unexpected(*args, **kwargs):
        pytest.fail("No network should be reached if the local report cannot be saved.")

    output = tmp_path / "report"
    monkeypatch.setenv("ANTESCOFO_API_KEY", KEY)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_test.py",
            "--base-url",
            API,
            "--audio",
            str(inputs["audio"]),
            "--score",
            str(inputs["score"]),
            "--output-dir",
            str(output),
            "--create-job",
        ],
    )
    # Report output creation is checked before touching quota.
    monkeypatch.setattr(AntescofoClient, "__init__", unexpected)

    def cannot_save(*args, **kwargs):
        raise OSError("Disk is read-only.")

    monkeypatch.setattr(smoke_test, "save", cannot_save)
    with pytest.raises(OSError, match="Disk is read-only"):
        smoke_test.main()
