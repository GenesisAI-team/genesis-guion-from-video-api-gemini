"""Adapter ffprobe: duración, pistas y metadatos del original (GEN-36).

Lee MOV/MP4 mediante ``ffprobe`` con salida JSON. Nunca modifica el original
(solo lectura), no crea ficheros temporales y clasifica cada fallo en un tipo
de excepción explícito.

El runner es inyectable para tests deterministas; el binario real solo se
ejecuta con ``DEFAULT_RUNNER`` (y en ``tests/integration``).
"""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any, Final

from pydantic import ValidationError

from genesis_video_ai.models.contracts import (
    MediaContainer,
    SourceMedia,
    StreamInfo,
    StreamKind,
)

DEFAULT_MAX_FILE_BYTES: Final = 4 * 1024**3
DEFAULT_FFPROBE_PATH: Final = "ffprobe"
FORMATO_JSON: Final = "json"
_CONTAINERS_BY_SUFFIX: Final[Mapping[str, MediaContainer]] = {"mov": "mov", "mp4": "mp4"}
_SUPPORTED_FORMAT_TOKENS: Final[frozenset[str]] = frozenset({"mov", "mp4"})

FFProbeRunner = Callable[[Sequence[str]], CompletedProcess[str]]


class AnalysisError(ValueError):
    """Base de los fallos del análisis técnico del material."""


class SourceNotFoundError(AnalysisError):
    """El original no existe o la ruta no apunta a un archivo."""


class UnsupportedContainerError(AnalysisError):
    """El contenedor no es MOV ni MP4."""


class FileSizeLimitExceededError(AnalysisError):
    """El original supera el límite de peso admitido."""


class FFProbeNotFoundError(AnalysisError):
    """El ejecutable ffprobe no está disponible en el sistema."""


class FFProbeFailedError(AnalysisError):
    """ffprobe no pudo procesar el archivo."""

    def __init__(self, mensaje: str, *, returncode: int | None = None) -> None:
        super().__init__(mensaje)
        self.returncode = returncode


class FFProbeOutputError(AnalysisError):
    """La salida de ffprobe no es JSON válido o no tiene la estructura esperada."""


def _default_runner(args: Sequence[str]) -> CompletedProcess[str]:
    """Ejecuta ffprobe capturando salida en texto (utf-8, tolerante a bytes raros)."""
    return subprocess.run(
        args, check=False, capture_output=True, encoding="utf-8", errors="replace"
    )


DEFAULT_RUNNER: Final[FFProbeRunner] = _default_runner


def probe_video(
    path: Path | str,
    *,
    runner: FFProbeRunner = DEFAULT_RUNNER,
    ffprobe_path: str = DEFAULT_FFPROBE_PATH,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> SourceMedia:
    """Analiza un MOV/MP4 y devuelve su contrato de fuente original.

    Args:
        path: Ruta del original (solo lectura, nunca se copia ni se toca).
        runner: Inyección para tests; por defecto ejecuta ``ffprobe`` real.
        ffprobe_path: Ejecutable a invocar.
        max_file_bytes: Límite de peso del archivo original.

    Returns:
        La fuente original con duración real, pistas y metadatos.

    Raises:
        SourceNotFoundError: Si la ruta no existe o no es archivo.
        UnsupportedContainerError: Si el sufijo o el formato no son mov/mp4.
        FileSizeLimitExceededError: Si el archivo supera el límite de peso.
        FFProbeNotFoundError: Si ffprobe no está instalado.
        FFProbeFailedError: Si ffprobe termina con error u OSError no controlado.
        FFProbeOutputError: Si la salida de ffprobe no es interpretable.
    """
    ruta = Path(path)
    _check_source(ruta)
    container = _container_from_suffix(ruta)
    size_bytes = ruta.stat().st_size
    if size_bytes > max_file_bytes:
        msg = (
            f"El original pesa {size_bytes} bytes, por encima del límite {max_file_bytes}: "
            "solo se analizan archivos temporales de sesión dentro del límite"
        )
        raise FileSizeLimitExceededError(msg)

    run = _execute_probe(ruta, ffprobe_path, runner)
    duration_s, format_name, metadata, streams = _parse_report(run)
    return SourceMedia(
        path=ruta.resolve(),
        container=container,
        duration_s=duration_s,
        size_bytes=size_bytes,
        format_name=format_name,
        streams=streams,
        metadata=metadata,
    )


def _check_source(ruta: Path) -> None:
    if not ruta.exists():
        msg = f"El original no existe: {ruta}"
        raise SourceNotFoundError(msg)
    if not ruta.is_file():
        msg = f"La ruta del original no es un archivo: {ruta}"
        raise SourceNotFoundError(msg)


def _container_from_suffix(ruta: Path) -> MediaContainer:
    suffix = ruta.suffix.lower().lstrip(".")
    container = _CONTAINERS_BY_SUFFIX.get(suffix)
    if container is None:
        msg = f"Solo se analizan los contenedores mov y mp4, recibido sufijo {suffix!r}"
        raise UnsupportedContainerError(msg)
    return container


def _execute_probe(ruta: Path, ffprobe_path: str, runner: FFProbeRunner) -> CompletedProcess[str]:
    """Invoca ffprobe con salida JSON completa y clasifica el fallo de arranque."""
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        FORMATO_JSON,
        "-show_format",
        "-show_streams",
        str(ruta),
    ]
    try:
        return runner(command)
    except FileNotFoundError as exc:
        msg = f"ffprobe no está disponible en el sistema: {exc}"
        raise FFProbeNotFoundError(msg) from exc
    except OSError as exc:
        msg = f"No se pudo ejecutar ffprobe: {exc!r}"
        raise FFProbeFailedError(msg) from exc


def _parse_report(
    run: CompletedProcess[str],
) -> tuple[float, str, Mapping[str, str], tuple[StreamInfo, ...]]:
    """Convierte la salida JSON de ffprobe en datos tipados y validados."""
    if run.returncode != 0:
        stderr = (run.stderr or "").strip()
        msg = f"ffprobe falló con código {run.returncode}: {stderr}"
        raise FFProbeFailedError(msg, returncode=run.returncode)

    payload = _parse_json(run.stdout or "")
    format_raw = _section(payload, "format")
    streams_raw = payload.get("streams")
    if not isinstance(streams_raw, list):
        msg = "La salida de ffprobe no lista 'streams'"
        raise FFProbeOutputError(msg)

    duration_s = _parse_duration(format_raw)
    format_name = _parse_format_name(format_raw)
    metadata = _parse_tags(format_raw.get("tags"))
    streams = tuple(_stream_info(stream_raw) for stream_raw in streams_raw)
    return duration_s, format_name, metadata, streams


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"La salida de ffprobe no es un JSON válido: {exc}"
        raise FFProbeOutputError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"La salida de ffprobe no es un objeto JSON: {type(payload).__name__}"
        raise FFProbeOutputError(msg)
    return payload


def _section(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    section = payload.get(key)
    if not isinstance(section, dict):
        msg = f"La salida de ffprobe no contiene la sección {key!r}"
        raise FFProbeOutputError(msg)
    return section


def _parse_duration(fmt: Mapping[str, Any]) -> float:
    raw = fmt.get("duration")
    if raw is None:
        msg = "La salida de ffprobe no reporta 'duration'"
        raise FFProbeOutputError(msg)
    try:
        duration_s = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"La duración de ffprobe no es numérica: {raw!r}"
        raise FFProbeOutputError(msg) from exc
    if not math.isfinite(duration_s) or duration_s <= 0:
        msg = f"La duración de ffprobe no es válida: {duration_s!r}"
        raise FFProbeOutputError(msg)
    return duration_s


def _parse_format_name(fmt: Mapping[str, Any]) -> str:
    format_name = fmt.get("format_name")
    if not isinstance(format_name, str) or not format_name.strip():
        msg = "La salida de ffprobe no reporta 'format_name'"
        raise FFProbeOutputError(msg)
    tokens = {token.strip().lower() for token in format_name.split(",")}
    if not tokens & _SUPPORTED_FORMAT_TOKENS:
        msg = f"El formato de ffprobe {format_name!r} no pertenece a los contenedores mov/mp4"
        raise UnsupportedContainerError(msg)
    return format_name


def _parse_tags(raw: Any) -> dict[str, str]:
    """Conserva solo etiquetas texto-texto; descarta valores ilegibles."""
    if not isinstance(raw, Mapping):
        return {}
    return {
        key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)
    }


def _stream_info(raw_stream: Any) -> StreamInfo:
    if not isinstance(raw_stream, dict):
        msg = f"La salida de ffprobe contiene una pista no válida: {raw_stream!r}"
        raise FFProbeOutputError(msg)

    index = _mandatory_index(raw_stream)
    kind = _stream_kind(raw_stream.get("codec_type"))
    codec = raw_stream.get("codec_name")
    tags = raw_stream.get("tags")
    language = tags.get("language") if isinstance(tags, Mapping) else None
    try:
        return StreamInfo(
            index=index,
            kind=kind,
            codec=codec if isinstance(codec, str) else None,
            duration_s=_optional_float(raw_stream.get("duration"), "duration"),
            width=_optional_int(raw_stream.get("width"), "width"),
            height=_optional_int(raw_stream.get("height"), "height"),
            fps=_parse_rate(raw_stream.get("avg_frame_rate")),
            language=language if isinstance(language, str) else None,
        )
    except ValidationError as exc:
        msg = f"La pista de ffprobe no cumple los contratos: {exc}"
        raise FFProbeOutputError(msg) from exc


def _mandatory_index(raw_stream: Mapping[str, Any]) -> int:
    raw = raw_stream.get("index")
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"La salida de ffprobe contiene una pista sin índice numérico: {raw!r}"
        raise FFProbeOutputError(msg) from exc


def _stream_kind(codec_type: Any) -> StreamKind:
    if codec_type == "video":
        return "video"
    if codec_type == "audio":
        return "audio"
    return "other"


def _optional_int(raw: Any, field: str) -> int | None:
    """None, '' y 'N/A' son medidas ausentes; lo demás debe ser numérico."""
    if raw is None or raw == "" or raw == "N/A":
        return None
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"La pista de ffprobe tiene un valor ilegible en {field!r}: {raw!r}"
        raise FFProbeOutputError(msg) from exc


def _optional_float(raw: Any, field: str) -> float | None:
    if raw is None or raw == "" or raw == "N/A":
        return None
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        msg = f"La pista de ffprobe tiene un valor ilegible en {field!r}: {raw!r}"
        raise FFProbeOutputError(msg) from exc
    return value if math.isfinite(value) else None


def _parse_rate(raw: Any) -> float | None:
    """Convierte '25/1' en 25.0; las notaciones nulas de ffprobe quedan sin datos."""
    if raw is None or (isinstance(raw, str) and raw in {"", "N/A", "0/0"}):
        return None
    if not isinstance(raw, str):
        msg = f"La pista de ffprobe tiene un avg_frame_rate ilegible: {raw!r}"
        raise FFProbeOutputError(msg)
    numerator_text, separator, denominator_text = raw.partition("/")
    if not separator:
        msg = f"La pista de ffprobe tiene un avg_frame_rate ilegible: {raw!r}"
        raise FFProbeOutputError(msg)
    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except ValueError as exc:
        msg = f"La pista de ffprobe tiene un avg_frame_rate ilegible: {raw!r}"
        raise FFProbeOutputError(msg) from exc
    if denominator == 0:
        return None
    rate = numerator / denominator
    return rate if math.isfinite(rate) and rate > 0 else None
