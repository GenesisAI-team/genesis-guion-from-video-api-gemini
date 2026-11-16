"""Constructor del prompt de generación de guiones (GEN-45).

Infraestructura determinista: describe el original, el material real adjunto
(grounding: archivos y anotaciones de contenido), el material medido y el
formato JSON esperado. No decide nada editorial: la validación de lo que el
modelo devuelva vive en ``editorial/script_validation.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from genesis_video_ai.gemini.port import ScriptProposalRequest

if TYPE_CHECKING:
    from genesis_video_ai.gemini.grounding import GroundingMaterial


def build_script_prompt(request: ScriptProposalRequest, material: GroundingMaterial) -> str:
    """Construye el prompt con el material real, el medido y el esquema de respuesta."""
    lines = [
        "Eres un montador audiovisual estricto. Debes proponer un guion",
        "utilizando ÚNICAMENTE el material real listado abajo.",
        "",
        "Original:",
        f"- source_id: {request.source.id}",
        f"- contenedor: {request.source.container}",
        f"- duración real: {request.source.duration_s!r} s",
        "",
        "Material real adjunto a esta petición (tu única evidencia):",
    ]
    lines.extend(f"  - archivo original: {path}" for path in material.media)

    if material.annotations:
        lines.append(f"  - anotaciones de contenido ({len(material.annotations)}):")
        lines.extend(
            f"    {index}. ventana [{annotation.start_s!r}, {annotation.end_s!r}] "
            f'{annotation.kind}: "{annotation.text}"'
            for index, annotation in enumerate(material.annotations, start=1)
        )
    else:
        lines.append("  - anotaciones de contenido: ninguna")

    lines.extend(
        [
            "",
            f"Material medido disponible ({len(request.segments)} segmentos):",
        ]
    )
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
            "- Narración y justificación ancladas: cada declaración debe derivar del",
            "  material real adjunto (archivo y/o anotaciones); no inventes escenas,",
            "  hechos ni afirmaciones que no estén en él.",
            "",
            "Responde ÚNICAMENTE con un objeto JSON (sin texto adicional) con",
            "esta forma:",
            '{"entries": [{"start_s": <float>, "end_s": <float>,',
            '  "narration": <texto de la locución>,',
            '  "justification": <por qué ese tramo sirve>}]}',
        ]
    )
    return "\n".join(lines)
