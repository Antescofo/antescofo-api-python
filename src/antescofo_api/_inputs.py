"""Validate input paths; never transcode, inspect duration, or modify files."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Inputs:
    audio: Path
    score: Path
    audio_format: str


def prepare_inputs(
    audio: str | Path,
    score: str | Path,
) -> Inputs:
    audio_path = validate_file(audio, {".mp3", ".wav"}, "Audio")
    score_path = validate_file(score, {".xml", ".musicxml"}, "Score")
    return Inputs(audio_path, score_path, audio_path.suffix[1:].lower())


def validate_file(value: str | Path, extensions: set[str], label: str) -> Path:
    path = Path(value)
    if path.suffix.lower() not in extensions:
        raise ValueError(f"{label} must use one of: {', '.join(sorted(extensions))}.")
    if not path.is_file():
        raise ValueError(f"{label} file does not exist or is not a regular file.")
    if path.stat().st_size == 0:
        raise ValueError(f"{label} file is empty.")
    with path.open("rb"):
        pass
    return path


def positive_seconds(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number greater than zero.")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero.")
    return float(value)
