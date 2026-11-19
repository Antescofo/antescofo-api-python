import json
from uuid import UUID

import pytest

from antescofo_api import ProtocolError
from antescofo_api._inputs import positive_seconds, prepare_inputs
from antescofo_api.models import parse_job

from .conftest import JOB_ID, job_payload


def test_wav_paths_are_validated_without_conversion(inputs):
    before = inputs["audio"].read_bytes()
    prepared = prepare_inputs(**inputs)
    assert prepared.audio_format == "wav"
    assert prepared.score == inputs["score"]
    assert inputs["audio"].read_bytes() == before


def test_mp3_paths_do_not_require_duration_metadata(inputs):
    path = inputs["audio"].with_suffix(".MP3")
    path.write_bytes(b"mock audio header")
    prepared = prepare_inputs(path, inputs["score"])
    assert prepared.audio_format == "mp3"
    assert prepared.audio.read_bytes() == b"mock audio header"


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "91", None])
def test_invalid_seconds(value):
    with pytest.raises(ValueError):
        positive_seconds(value, "duration")


@pytest.mark.parametrize("change", ["missing_audio", "empty_score", "wrong_audio", "wrong_score"])
def test_invalid_inputs_consume_no_job(client, inputs, requests_mock, change):
    if change == "missing_audio":
        inputs["audio"].unlink()
    elif change == "empty_score":
        inputs["score"].write_text("")
    elif change == "wrong_audio":
        inputs["audio"] = inputs["audio"].with_suffix(".flac")
    else:
        inputs["score"] = inputs["score"].with_suffix(".mxl")
    with pytest.raises(ValueError):
        client.performance_analyzer.submit(**inputs)
    assert not requests_mock.called


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        job_payload(uuid="bad"),
        job_payload(uuid=None),
        job_payload(uuid=42),
        job_payload(uuid=[]),
        job_payload(status=[]),
        job_payload(error=[]),
        job_payload(upload_urls=[]),
        job_payload(upload_urls={"audio": 3}),
        job_payload(file_duration=-1),
        job_payload(file_duration=True),
        job_payload(module=42),
        job_payload(created_at=42),
        job_payload(finished_at=42),
    ],
)
def test_invalid_job_schema(payload):
    with pytest.raises(ProtocolError):
        parse_job(payload)


@pytest.mark.parametrize("identifier", [JOB_ID, JOB_ID.upper(), UUID(JOB_ID).hex])
def test_job_id_is_a_uuid(identifier):
    job = parse_job(job_payload(uuid=identifier))
    assert isinstance(job.id, UUID)
    assert job.id == UUID(JOB_ID)


def test_job_dictionary_omits_signed_urls_and_files():
    job = parse_job(
        job_payload(
            upload_urls={"score": "https://private.example/signed"},
            files=["https://private.example/result"],
        )
    )
    assert job.to_dict()["uuid"] == JOB_ID
    assert "upload_urls" not in job.to_dict()
    assert "files" not in job.to_dict()
    snapshot = json.loads(json.dumps(job.to_dict()))
    restored = parse_job(snapshot)
    assert restored.id == job.id
    assert isinstance(restored.id, UUID)
    assert restored.to_dict() == snapshot
    assert restored.upload_urls == {}
