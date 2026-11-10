"""Tests del adaptador del SDK google-genai (GEN-45).

El SDK solo se importa perezosamente dentro del adaptador; los tests usan
stub de módulo para no realizar jamás una llamada real.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.errors import (
    GeminiAuthError,
    GeminiInvalidResponseError,
    GeminiNotAvailableError,
    GeminiQuotaExceededError,
    GeminiRequestError,
    GeminiTimeoutError,
)
from genesis_video_ai.gemini.response import ScriptPayload
from genesis_video_ai.gemini.sdk_adapter import GoogleGenaiScriptSession, map_api_error


class StubHttpOptions:
    """Sustituto de types.HttpOptions que registra sus kwargs."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class StubModels:
    """Sustituto de client.models con comportamiento programable."""

    def __init__(self, session: StubSession) -> None:
        self._session = session

    def generate_content(self, **kwargs: Any) -> Any:
        self._session.calls.append(kwargs)
        return self._session.next_result()


class StubSession:
    """Cliente falso compatible con la forma usada por el adaptador."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result
        self._error = error

    def next_result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


class StubAPIError(Exception):
    """Sustituto de google.genai.errors.APIError."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def install_google_stub(monkeypatch: pytest.MonkeyPatch, client: StubSession) -> None:
    """Registra un módulo google.genai falso en sys.modules."""
    types_stub = types.ModuleType("google.genai.types")
    types_stub.HttpOptions = StubHttpOptions  # type: ignore[attr-defined]

    errors_stub = types.ModuleType("google.genai.errors")
    errors_stub.APIError = StubAPIError  # type: ignore[attr-defined]

    genai_stub = types.ModuleType("google.genai")
    genai_stub.types = types_stub  # type: ignore[attr-defined]
    genai_stub.errors = errors_stub  # type: ignore[attr-defined]

    genai_root = types.ModuleType("google")

    class StubClient:
        def __init__(self, **kwargs: Any) -> None:
            client.constructor_kwargs = kwargs  # type: ignore[attr-defined]
            self.models = StubModels(client)

    genai_stub.Client = StubClient  # type: ignore[attr-defined]
    genai_root.genai = genai_stub  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "google", genai_root)
    monkeypatch.setitem(sys.modules, "google.genai", genai_stub)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_stub)
    monkeypatch.setitem(sys.modules, "google.genai.errors", errors_stub)


def make_text_response(text: str) -> Any:
    return types.SimpleNamespace(text=text)


# --- mapa de errores ----------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, GeminiQuotaExceededError),
        (401, GeminiAuthError),
        (403, GeminiAuthError),
        (408, GeminiTimeoutError),
        (400, GeminiRequestError),
        (500, GeminiRequestError),
        (503, GeminiRequestError),
    ],
)
def test_map_api_error_clasifica_por_codigo(code: int, expected: type[GeminiRequestError]) -> None:
    error = map_api_error(code, "mensaje de la API")

    assert type(error) is expected
    assert "mensaje de la API" in str(error)


def test_auth_error_es_tambien_no_disponible() -> None:
    error = map_api_error(403, "sin permisos")

    assert isinstance(error, GeminiNotAvailableError)


# --- sesión adaptadora --------------------------------------------------------


def test_sesion_sin_clave_no_esta_disponible() -> None:
    with pytest.raises(GeminiNotAvailableError, match="credencial"):
        GoogleGenaiScriptSession(GeminiClientConfig(api_key=None))


def test_sesion_construye_el_cliente_con_la_clave_y_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = StubSession(result=make_text_response("{}"))
    install_google_stub(monkeypatch, stub)
    config = GeminiClientConfig(api_key="clave-falsa", timeout_s=45.0)

    session = GoogleGenaiScriptSession(config)

    assert session._client is not None
    assert stub.constructor_kwargs["api_key"] == "clave-falsa"
    assert stub.constructor_kwargs["http_options"].kwargs["timeout"] == 45000


def test_generate_envia_modelo_prompt_y_esquema(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubSession(result=make_text_response('{"entries": []}'))
    install_google_stub(monkeypatch, stub)
    session = GoogleGenaiScriptSession(
        GeminiClientConfig(api_key="clave-falsa", max_output_tokens=1024, temperature=0.1)
    )

    raw = session.generate("prompt de prueba", ScriptPayload)

    assert raw == '{"entries": []}'
    call = stub.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "prompt de prueba"
    assert call["config"]["response_mime_type"] == "application/json"
    assert call["config"]["response_schema"] is ScriptPayload
    assert call["config"]["max_output_tokens"] == 1024
    assert call["config"]["temperature"] == pytest.approx(0.1)


def test_generate_devuelve_respuesta_vacia_como_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = StubSession(result=make_text_response(None))
    install_google_stub(monkeypatch, stub)
    session = GoogleGenaiScriptSession(GeminiClientConfig(api_key="clave-falsa"))

    with pytest.raises(GeminiInvalidResponseError, match="vac"):
        session.generate("prompt", ScriptPayload)


def test_generate_traduce_errores_de_la_api(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubSession(error=StubAPIError(429, "RESOURCE_EXHAUSTED"))
    install_google_stub(monkeypatch, stub)
    session = GoogleGenaiScriptSession(GeminiClientConfig(api_key="clave-falsa"))

    with pytest.raises(GeminiQuotaExceededError, match="RESOURCE_EXHAUSTED"):
        session.generate("prompt", ScriptPayload)


def test_generate_traduce_errores_no_sdk_como_peticion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = StubSession(error=ValueError("fallo local"))
    install_google_stub(monkeypatch, stub)
    session = GoogleGenaiScriptSession(GeminiClientConfig(api_key="clave-falsa"))

    with pytest.raises(GeminiRequestError, match="fallo local"):
        session.generate("prompt", ScriptPayload)
