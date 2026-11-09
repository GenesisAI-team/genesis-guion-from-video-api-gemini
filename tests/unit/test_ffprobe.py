"""Tests del adapter ffprobe: duración, pistas y metadatos (GEN-36 §2).

Todos los tests son deterministas: el runner de ffprobe se inyecta, jamás se
ejecuta un binario real desde los unitarios. Los ficheros reales viven en
``tests/integration``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from genesis_video_ai.analysis.ffprobe import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_RUNNER,
    FFProbeFailedError,
    FFProbeNotFoundError,
    FFProbeOutputError,
    FFProbeRunner,
    FileSizeLimitExceededError,
    SourceNotFoundError,
    UnsupportedContainerError,
    probe_video,
)


def make_media(tmp_path: Path, suffix: str = ".mp4", content: bytes = b"x") -> Path:
    """Crea un archivo de prueba con un sufijo dado."""
    media = tmp_path / f"original{suffix}"
    media.write_bytes(content)
    return media


def make_runner(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> tuple[FFProbeRunner, list[Sequence[str]]]:
    """Factoría de un runner determinista que registra las invocaciones."""
    calls: list[Sequence[str]] = []

    def runner(args: Sequence[str]) -> CompletedProcess[str]:
        calls.append(list(args))
        return CompletedProcess(
            args=list(args), returncode=returncode, stdout=stdout, stderr=stderr
        )

    return runner, calls


def probe_payload(
    *,
    duration: str | float | None = "42.5",
    format_name: str | None = "mov,mp4,m4a,3gp,3g2,mj2",
    streams: list[dict[str, object]] | None = None,
    tags: dict[str, str] | None = None,
) -> dict[str, object]:
    """Salida JSON mínima de ffprobe para MOV/MP4."""
    if streams is None:
        streams = [video_stream_payload()]
    fmt: dict[str, object] = {"nb_streams": len(streams)}
    if duration is not None:
        fmt["duration"] = duration
    if format_name is not None:
        fmt["format_name"] = format_name
    if tags is not None:
        fmt["tags"] = tags
    return {"streams": streams, "format": fmt}


def video_stream_payload(
    *,
    duration: object | None = "42.500000",
    avg_frame_rate: object | None = "25/1",
    width: object | None = 1920,
    height: object | None = 1080,
    codec: str | None = "h264",
    tags: dict[str, str] | None = None,
) -> dict[str, object]:
    """Pista de vídeo de ejemplo."""
    stream: dict[str, object] = {
        "index": 0,
        "codec_type": "video",
        "codec_name": codec,
    }
    if duration is not None:
        stream["duration"] = duration
    if avg_frame_rate is not None:
        stream["avg_frame_rate"] = avg_frame_rate
    if width is not None:
        stream["width"] = width
    if height is not None:
        stream["height"] = height
    if tags is not None:
        stream["tags"] = tags
    return stream


def run_probe(media: Path, runner: FFProbeRunner, **kwargs: object) -> object:
    """Helper tipado para invocar probe_video con kwargs arbitrarios."""
    result: object = probe_video(media, runner=runner, **kwargs)  # type: ignore[arg-type]
    return result


# --- recorrido feliz -------------------------------------------------------


def test_lee_duracion_contenedor_pistas_y_metadatos(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(
        duration="42.5",
        streams=[
            video_stream_payload(),
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "duration": "42.520000",
                "tags": {"language": "spa"},
            },
        ],
        tags={"major_brand": "isom", "com.apple.quicktime.software": "iPhone"},
    )
    runner, calls = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert source.path == media.resolve()  # type: ignore[attr-defined]
    assert source.container == "mp4"  # type: ignore[attr-defined]
    assert source.duration_s == pytest.approx(42.5)  # type: ignore[attr-defined]
    assert source.size_bytes == media.stat().st_size  # type: ignore[attr-defined]
    assert source.format_name == "mov,mp4,m4a,3gp,3g2,mj2"  # type: ignore[attr-defined]
    assert source.metadata["major_brand"] == "isom"  # type: ignore[attr-defined]
    assert len(source.streams) == 2  # type: ignore[attr-defined]

    video, audio = source.streams  # type: ignore[attr-defined]
    assert video.kind == "video"
    assert video.codec == "h264"
    assert video.width == 1920
    assert video.height == 1080
    assert video.fps == pytest.approx(25.0)
    assert video.duration_s == pytest.approx(42.5)
    assert video.language is None
    assert audio.kind == "audio"
    assert audio.fps is None
    assert audio.width is None
    assert audio.language == "spa"

    args = list(calls[0])
    assert args[0] == "ffprobe"
    assert args[1:7] == ["-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    assert args[-1] == str(media.resolve())


def test_contenedor_mov_por_extension(tmp_path: Path) -> None:
    media = make_media(tmp_path, suffix=".MOV")
    runner, _ = make_runner(stdout=json.dumps(probe_payload()))

    source = run_probe(media, runner)

    assert source.container == "mov"  # type: ignore[attr-defined]


def test_pistas_sin_datos_toleradas_como_otros(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(
        streams=[
            {"index": 3, "codec_type": "data"},
            {"index": 4, "codec_type": "subtitles"},
            {"index": 5, "codec_type": "attachment"},
            {"index": 6},
        ]
    )
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert [stream.kind for stream in source.streams] == ["other", "other", "other", "other"]  # type: ignore[attr-defined]
    assert all(stream.codec is None for stream in source.streams)  # type: ignore[attr-defined]


def test_campos_de_pista_fuera_de_formato_se_ignoran(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(
        streams=[
            {
                "index": 0,
                "codec_type": "video",
                "duration": "N/A",
                "avg_frame_rate": "0/0",
                "width": None,
                "height": "",
            }
        ]
    )
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    stream = source.streams[0]  # type: ignore[attr-defined]
    assert stream.fps is None
    assert stream.duration_s is None
    assert stream.width is None
    assert stream.height is None


def test_fps_fraccionario_no_entero(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[video_stream_payload(avg_frame_rate="24000/1001")])
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert source.streams[0].fps == pytest.approx(23.976, abs=0.01)  # type: ignore[attr-defined]


def test_etiquetas_de_formato_no_validas_se_descartan(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[], tags={"la válida": "texto"})
    payload["format"]["tags"]["rara"] = None  # type: ignore[index]
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert source.metadata == {"la válida": "texto"}  # type: ignore[attr-defined]


def test_fuente_reproducible_sin_id_impuesta(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    runner, _ = make_runner(stdout=json.dumps(probe_payload()))

    first = run_probe(media, runner)
    second = run_probe(media, runner)

    assert first.id != second.id  # type: ignore[attr-defined]


# --- errores clasificados ---------------------------------------------------


def test_archivo_inexistente_rechazado(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError, match="no existe"):
        run_probe(tmp_path / "quitado.mp4", make_runner()[0])


def test_ruta_directorio_rechazada(tmp_path: Path) -> None:
    with pytest.raises(SourceNotFoundError):
        run_probe(tmp_path, make_runner()[0])


@pytest.mark.parametrize("suffix", [".avi", ".mkv", ".mov.mp4.txt", ""])
def test_extension_no_soportada_rechazada_sin_probar(tmp_path: Path, suffix: str) -> None:
    media = make_media(tmp_path, suffix=suffix or ".bin")
    runner, calls = make_runner(stdout=json.dumps(probe_payload()))

    with pytest.raises(UnsupportedContainerError, match=r"mov|mp4"):
        run_probe(media, runner)

    assert calls == []


def test_peso_por_encima_del_limite_rechazado(tmp_path: Path) -> None:
    media = make_media(tmp_path, content=b"x" * 12)
    runner, calls = make_runner(stdout=json.dumps(probe_payload()))

    with pytest.raises(FileSizeLimitExceededError, match="12"):
        run_probe(media, runner, max_file_bytes=11)

    assert calls == []


def test_limite_de_peso_4_gib_por_defecto() -> None:
    assert DEFAULT_MAX_FILE_BYTES == 4 * 1024**3


def test_ejecutable_inexistente_clasificado(tmp_path: Path) -> None:
    media = make_media(tmp_path)

    def fallo(args: Sequence[str]) -> CompletedProcess[str]:
        raise FileNotFoundError("El sistema no puede encontrar el archivo especificado")

    with pytest.raises(FFProbeNotFoundError, match="ffprobe"):
        run_probe(media, fallo)


def test_error_de_ejecucion_del_sistema(tmp_path: Path) -> None:
    media = make_media(tmp_path)

    def fallo(args: Sequence[str]) -> CompletedProcess[str]:
        raise PermissionError("[Errno 32] proceso no lanzable")

    with pytest.raises(FFProbeFailedError, match="32"):
        run_probe(media, fallo)


def test_salida_de_ffprobe_fallida(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    runner, _ = make_runner(returncode=1, stderr="Invalid data found when processing input")

    with pytest.raises(FFProbeFailedError) as excinfo:
        run_probe(media, runner)

    assert "Invalid data found" in str(excinfo.value)


def test_salida_json_invalida(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    runner, _ = make_runner(stdout="{no es json")

    with pytest.raises(FFProbeOutputError, match="JSON"):
        run_probe(media, runner)


def test_salida_json_no_diccionario(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    runner, _ = make_runner(stdout=json.dumps([1, 2]))

    with pytest.raises(FFProbeOutputError, match="objeto"):
        run_probe(media, runner)


@pytest.mark.parametrize(
    "payload",
    [
        {"streams": [], "format": {}},  # sin duración
        {"streams": [], "format": {"duration": "N/A"}},  # duración no numérica
        {"streams": [], "format": {"duration": "-3"}},  # negativa
        {"streams": [], "format": {"duration": "0"}},  # cero
        {"streams": [], "format": {"duration": "inf"}},  # infinita
        {"streams": [], "format": {"duration": 10}},  # sin format_name
        {"streams": [1], "format": {"duration": "10", "format_name": "mov,mp4"}},  # pista no dict
        {"format": {"duration": "10", "format_name": "mov,mp4"}},  # sin clave streams
        {"streams": []},  # sin sección format
        {
            "streams": [{"index": "cero", "codec_type": "video"}],
            "format": {"duration": "1", "format_name": "mov,mp4"},
        },  # índice no numérico
    ],
)
def test_salida_estructura_invalida(tmp_path: Path, payload: object) -> None:
    media = make_media(tmp_path)
    runner, _ = make_runner(stdout=json.dumps(payload))

    with pytest.raises(FFProbeOutputError):
        run_probe(media, runner)


def test_formato_fuera_de_mov_mp4_del_contenido_rechazado(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(format_name="matroska,webm")
    runner, _ = make_runner(stdout=json.dumps(payload))

    with pytest.raises(UnsupportedContainerError, match="matroska"):
        run_probe(media, runner)


def test_pista_invalida_contra_contratos(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[{"index": -1, "codec_type": "video", "duration": "1"}])
    runner, _ = make_runner(stdout=json.dumps(payload))

    with pytest.raises(FFProbeOutputError, match="pista"):
        run_probe(media, runner)


def test_registro_de_formato_no_diccionario_se_ignora(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[video_stream_payload()])
    payload["format"]["tags"] = 7  # type: ignore[assignment]
    payload["streams"][0]["tags"] = 7  # type: ignore[index]
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert source.metadata == {}  # type: ignore[attr-defined]
    assert source.streams[0].language is None  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("field", "basura"),
    [
        ("width", "no-numérico"),
        ("height", "no-numérico"),
        ("duration", "abc"),
        ("avg_frame_rate", "jjj"),
        ("avg_frame_rate", 25),
        ("avg_frame_rate", "25/la"),
    ],
)
def test_valores_de_pista_ilegibles_rechazados(tmp_path: Path, field: str, basura: object) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[{"index": 0, "codec_type": "video", field: basura}])
    runner, _ = make_runner(stdout=json.dumps(payload))

    with pytest.raises(FFProbeOutputError, match="pista"):
        run_probe(media, runner)


def test_fps_con_denominador_cero_se_ignora(tmp_path: Path) -> None:
    media = make_media(tmp_path)
    payload = probe_payload(streams=[video_stream_payload(avg_frame_rate="25/0")])
    runner, _ = make_runner(stdout=json.dumps(payload))

    source = run_probe(media, runner)

    assert source.streams[0].fps is None  # type: ignore[attr-defined]


# --- runner por defecto ------------------------------------------------------


def test_runner_por_defecto_delega_en_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """El runner por defecto delega en subprocess con captura de salida en texto."""
    expected = CompletedProcess(args=["ffprobe"], returncode=0, stdout="", stderr="")
    seen_calls: list[list[str]] = []

    def fake_run(args: Sequence[str], **kwargs: object) -> CompletedProcess[str]:
        seen_calls.append(list(args))
        assert kwargs["capture_output"] is True
        return expected

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = DEFAULT_RUNNER(["ffprobe", "-v", "error"])

    assert result is expected
    assert seen_calls == [["ffprobe", "-v", "error"]]
