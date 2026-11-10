"""Constructor del prompt de generación de guiones (GEN-45).

Infraestructura determinista: describe el original, el material medido y el
formato JSON esperado. No decide nada editorial: la validación de lo que el
modelo devuelva vive en ``editorial/script_validation.py``.
"""

from __future__ import annotations

from genesis_video_ai.gemini.port import ScriptProposalRequest


def build_script_prompt(request: ScriptProposalRequest) -> str:
    """Construye el prompt con el material medido y el esquema de respuesta."""
    lines = [
        "Eres un montador audiovisual estricto. Debes proponer un guion",
        "utilizando ÚNICAMENTE el material real listado abajo.",
        "",
        "Original:",
        f"- source_id: {request.source.id}",
        f"- contenedor: {request.source.container}",
        f"- duración real: {request.source.duration_s!r} s",
        "",
        f"Material medido disponible ({len(request.segments)} segmentos):",
    ]
    for index, segment in enumerate(request.segments, start=1):
        lines.append(
            f"  {index}. ventana [{segment.start_s!r}, {segment.end_s!r}] "
            f"duración {segment.duration_s!r} s"
        )

    lines.extend(
        [
            "",
            f"Duración pedida del guion: {request.requested_duration_s!r} s",
            "",
            "Reglas inquebrantables:",
            "- No inventes material: cada tramo debe estar contenido dentro de",
            "  una de las ventanas medidas listadas arriba.",
            "- Los tramos no pueden solaparse y deben referenciar el original.",
            "- No propongas tiempos fuera del material medido.",
            "",
            "Responde ÚNICAMENTE con un objeto JSON (sin texto adicional) con",
            "esta forma:",
            '{"entries": [{"start_s": <float>, "end_s": <float>,',
            '  "narration": <texto de la locución>,',
            '  "justification": <por qué ese tramo sirve>}]}',
        ]
    )
    return "\n".join(lines)
