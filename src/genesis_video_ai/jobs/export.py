"""Exportación de guiones a JSON y Markdown (GEN-50).

Último paso del flujo de trabajos: el guion propuesto se escribe donde el
usuario decida, siempre con la fuente real (ruta absoluta del original,
contenedor y duración medida) y los tiempos in/out de cada tramo. Las
exportaciones son verificables: nada se calcula fuera de las entradas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from genesis_video_ai.gemini.port import ScriptEntry, ScriptProposal
from genesis_video_ai.models.contracts import SourceMedia


def export_proposal_json(
    proposal: ScriptProposal,
    source: SourceMedia,
    path: Path | str,
) -> Path:
    """Escribe la propuesta como JSON trazable y devuelve la ruta escrita.

    Raises:
        ValueError: Si la propuesta no referencia el original dado.
    """
    _check_proposal_source(proposal, source)
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_payload(proposal, source)
    destino.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destino


def export_proposal_markdown(
    proposal: ScriptProposal,
    source: SourceMedia,
    path: Path | str,
) -> Path:
    """Escribe la propuesta como Markdown legible y devuelve la ruta escrita.

    Raises:
        ValueError: Si la propuesta no referencia el original dado.
    """
    _check_proposal_source(proposal, source)
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(_markdown_text(proposal, source), encoding="utf-8")
    return destino


def _check_proposal_source(proposal: ScriptProposal, source: SourceMedia) -> None:
    """La exportación solo es válida para el original que se validó."""
    if proposal.source_id != source.id:
        msg = (
            f"La propuesta referencia el original {proposal.source_id!r}, "
            f"no {source.id!r}: la exportación sería inverifyificable"
        )
        raise ValueError(msg)


def _json_payload(proposal: ScriptProposal, source: SourceMedia) -> dict[str, Any]:
    return {
        "source": _json_source(source),
        "requested_duration_s": proposal.requested_duration_s,
        "total_duration_s": proposal.total_duration_s,
        "entries": [_json_entry(index, entry) for index, entry in enumerate(proposal.entries, 1)],
    }


def _json_source(source: SourceMedia) -> dict[str, Any]:
    return {
        "id": source.id,
        "path": str(source.path),
        "container": source.container,
        "duration_s": source.duration_s,
        "format_name": source.format_name,
    }


def _json_entry(index: int, entry: ScriptEntry) -> dict[str, Any]:
    return {
        "index": index,
        "source_id": entry.source_id,
        "start_s": entry.start_s,
        "end_s": entry.end_s,
        "duration_s": entry.duration_s,
        "narration": entry.narration,
        "justification": entry.justification,
    }


def _markdown_text(proposal: ScriptProposal, source: SourceMedia) -> str:
    lines = [
        "# Guion propuesto",
        "",
        f"- Original: `{source.path}`",
        f"- Contenedor: {source.container}",
        f"- Duración real del original: {_seconds(source.duration_s)} s",
        f"- Duración pedida: {_seconds(proposal.requested_duration_s)} s",
        f"- Duración total calculada: {_seconds(proposal.total_duration_s)} s",
        "",
        "| # | Entrada (s) | Salida (s) | Duración (s) | Narración |",
        "| ---: | ---: | ---: | ---: | --- |",
    ]
    for index, entry in enumerate(proposal.entries, 1):
        lines.append(
            f"| {index} | {_seconds(entry.start_s)} | {_seconds(entry.end_s)} | "
            f"{_seconds(entry.duration_s)} | {entry.narration} |"
        )
    lines.extend(["", "## Justificaciones", ""])
    lines.extend(
        f"{index}. {_seconds(entry.start_s)}-{_seconds(entry.end_s)} s: "
        f"{entry.justification or '—'}"
        for index, entry in enumerate(proposal.entries, 1)
    )
    return "\n".join(lines) + "\n"


def _seconds(value: float) -> str:
    """Segundos en texto compacto y exacto (45.0 -> "45", 0.5 -> "0.5")."""
    return f"{value:g}"
