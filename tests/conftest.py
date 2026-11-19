import wave

import pytest

from antescofo_api import AntescofoClient

API = "https://api.example"
JOB_ID = "550e8400-e29b-41d4-a716-446655440000"
OTHER_ID = "c1a16b66-7358-45a9-a33f-729d9c7629c9"
JOB_URL = f"{API}/v1/jobs/{JOB_ID}/"
SCORE_URL = "https://storage.example/score?signature=private-score"
AUDIO_URL = "https://storage.example/audio?signature=private-audio"
RESULT_URL = "https://storage.example/result?signature=private-result"
KEY = "test-member-key.not-a-real-secret"
RESULT = {
    "alignment_interop": [
        {
            "score_index": 0,
            "score_time": 0,
            "bpm": 90.5,
            "obs_time_ms": 10,
            "notes": [
                {
                    "pitch": 60,
                    "is_error": False,
                    "obs_time_ms": 10,
                    "onset_beat_deviation": -0.02,
                    "velocity": 0.7,
                    "probability": 0.95,
                },
                {"pitch": 64, "is_error": True, "error_type": "missing"},
                {"pitch": 65, "is_error": True, "error_type": "wrong_note", "obs_time_ms": 20},
                {"pitch": 67, "is_error": True, "error_type": "extra_note", "obs_time_ms": 30},
            ],
        }
    ],
    "assessment": {
        "overall": 85.5,
        "metrics": [
            {"key": "PitchPrecision", "label": "Pitch Precision", "value": 80},
        ],
    },
    "future_field": {"preserved": True},
}


@pytest.fixture(autouse=True)
def offline_http(requests_mock):
    """Reject all unregistered HTTP calls, even in tests that omit an explicit mock."""
    return requests_mock


def job_payload(status="succeeded", **overrides):
    return {
        "uuid": JOB_ID,
        "status": status,
        "module": "performance_analyzer",
        "file_duration": 91,
        "created_at": "2026-11-16T12:00:00Z",
        "finished_at": None,
        "error": None,
        **overrides,
    }


@pytest.fixture
def client():
    with AntescofoClient(KEY, base_url=API) as value:
        yield value


@pytest.fixture
def inputs(tmp_path):
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 10000)
    score = tmp_path / "score.musicxml"
    score.write_text('<score-partwise version="4.0"/>')
    return {"audio": audio, "score": score}


@pytest.fixture
def success_flow(requests_mock):
    requests_mock.post(
        f"{API}/v1/jobs/",
        status_code=201,
        json=job_payload(
            "pending",
            upload_urls={"score": SCORE_URL, "audio": AUDIO_URL},
        ),
    )
    requests_mock.put(SCORE_URL, status_code=200)
    requests_mock.put(AUDIO_URL, status_code=200)
    requests_mock.get(JOB_URL, json=job_payload())
    requests_mock.get(
        f"{JOB_URL}files/",
        json={
            "inputs": [],
            "outputs": [
                {"role": "other", "filename": "other.json", "url": "https://other.example"},
                {"role": "analysis", "filename": "result.json", "url": RESULT_URL},
            ],
        },
    )
    requests_mock.get(RESULT_URL, json=RESULT)
    return requests_mock
