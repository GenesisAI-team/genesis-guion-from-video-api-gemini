"""Flujo ffprobe -> segmentos -> validación editorial (GEN-36, trazabilidad).

Sin binarios reales: el runner se inyecta con una salida JSON sintética
determinista. Verifica que el contrato medido alimenta las reglas editoriales
y todo queda trazado al original.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from genesis_video_ai.analysis.ffprobe import probe_video
from genesis_video_ai.editorial.sequence import validate_segment_sequence
from genesis_video_ai.models.contracts import Segment

PAYLOAD: dict[str, object] = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1280,
            "height": 720,
            "avg_frame_rate": "25/1",
        },
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {
        "duration": "120.0",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "tags": {"major_brand": "isom"},
    },
}


def runner_de_prueba(args: Sequence[str]) -> CompletedProcess[str]:
    return CompletedProcess(args=list(args), returncode=0, stdout=json.dumps(PAYLOAD), stderr="")


def test_del_medido_al_guion_sin_inventar_material(tmp_path: Path) -> None:
    media = tmp_path / "original.mp4"
    media.write_bytes(b"x")

    source = probe_video(media, runner=runner_de_prueba)

    selection = [
        Segment(source_id=source.id, start_s=0.0, end_s=45.0),
        Segment(source_id=source.id, start_s=60.0, end_s=105.0),
    ]
    validated = validate_segment_sequence(
        selection,
        source=source,
        requested_duration_s=90.0,
    )

    assert [seg.start_s for seg in validated.ordered] == [0.0, 60.0]
    assert validated.total_s == pytest.approx(90.0)
    assert all(seg.source_id == source.id for seg in validated.ordered)


def test_la_medida_fija_los_limites_del_guion(tmp_path: Path) -> None:
    """El original medido fija los límites: nada puede apuntar más allá."""
    media = tmp_path / "original.mp4"
    media.write_bytes(b"x")
    source = probe_video(media, runner=runner_de_prueba)

    fuera = Segment(source_id=source.id, start_s=110.0, end_s=125.0)

    with pytest.raises(ValueError, match="125"):
        validate_segment_sequence([fuera], source=source, requested_duration_s=15.0)
