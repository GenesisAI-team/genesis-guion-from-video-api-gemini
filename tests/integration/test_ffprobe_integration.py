"""Análisis técnico real sobre fixtures sintéticos (GEN-36, aceptación).

Se ejecuta con el ffprobe del sistema contra MP4/MOV generados con ffmpeg.
Si los binarios no existen, la suite se salta (se reportan aparte, no cuentan
como éxito, según métrica del proyecto).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from genesis_video_ai.analysis.ffprobe import (
    FFProbeFailedError,
    probe_video,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="ffprobe no disponible en el sistema",
)


def test_probe_real_mp4(mp4_con_audio: Path) -> None:
    source = probe_video(mp4_con_audio)

    assert source.container == "mp4"
    assert source.duration_s == pytest.approx(0.5, abs=0.15)
    assert source.size_bytes == mp4_con_audio.stat().st_size
    kinds = [stream.kind for stream in source.streams]
    assert "video" in kinds
    assert "audio" in kinds
    video = source.streams[0]
    assert video.width == 64
    assert video.height == 36
    assert video.fps == pytest.approx(10.0)
    assert video.codec == "mpeg4"


def test_probe_real_mov(mov_solo_video: Path) -> None:
    source = probe_video(mov_solo_video)

    assert source.container == "mov"
    assert source.duration_s > 0
    assert source.streams[0].kind == "video"


def test_archivo_corrupto_rechazado_con_error_clasificado(tmp_path: Path) -> None:
    corrupto = tmp_path / "corrupto.mp4"
    corrupto.write_bytes(b"no-es-un-video" * 16)

    with pytest.raises(FFProbeFailedError, match="ffprobe fall"):
        probe_video(corrupto)
