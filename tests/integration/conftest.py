"""Fixture sintético MOV/MP4 generado con ffmpeg local (sin red)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBES_AVAILABLE = shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not (FFMPEG_AVAILABLE and FFPROBES_AVAILABLE),
    reason="ffmpeg/ffprobe no disponibles en el sistema",
)


@pytest.fixture(scope="session")
def mp4_con_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MP4 determinista: vídeo de barras + tono de 0,5 s."""
    root = tmp_path_factory.mktemp("fixtures")
    media = root / "sintetico.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x36:rate=10:duration=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(media),
        ],
        check=True,
        capture_output=True,
    )
    return media


@pytest.fixture(scope="session")
def mov_solo_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """MOV determinista: solo vídeo de barras de 0,5 s."""
    root = tmp_path_factory.mktemp("fixtures")
    media = root / "sintetico.mov"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x36:rate=10:duration=0.5",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "mov",
            str(media),
        ],
        check=True,
        capture_output=True,
    )
    return media
