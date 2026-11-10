"""Tests del cliente Gemini real detrás del puerto (GEN-45).

El cliente nunca llama a la API en tests: la sesión se inyecta como doble.
Cubre configuración, errores tipados, cuotas, plazo y cancelación.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest
from helpers import make_request

from genesis_video_ai.editorial.script_validation import InventedSegmentError
from genesis_video_ai.editorial.sequence import InsufficientMaterialError
from genesis_video_ai.gemini.client import RealGeminiScriptPort
from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.errors import (
    GeminiCancelledError,
    GeminiInvalidResponseError,
    GeminiNotAvailableError,
    GeminiQuotaExceededError,
    GeminiRequestError,
    GeminiTimeoutError,
)
from genesis_video_ai.gemini.port import GeminiScriptPort, ScriptProposal

VALID_JSON = (
    '{"entries": [{"start_s": 0.0, "end_s": 10.0, "narration": "Locución inicial",'
    ' "justification": "Tramo medido"}]}'
)
UNSORTED_JSON = (
    '{"entries": ['
    '{"start_s": 5.0, "end_s": 10.0, "narration": "Cierre", "justification": ""},'
    '{"start_s": 0.0, "end_s": 5.0, "narration": "Apertura", "justification": ""}'
    "]}"
)
INVENTED_JSON = '{"entries": [{"start_s": 20.0, "end_s": 28.5, "narration": "Nunca medido"}]}'
INSUFFICIENT_JSON = '{"entries": [{"start_s": 0.0, "end_s": 4.0, "narration": "Corto"}]}'


def make_window_json(start_s: float, end_s: float) -> str:
    """JSON de una entrada única trazable dentro del material medido."""
    return (
        '{"entries": [{"start_s": '
        + repr(start_s)
        + ', "end_s": '
        + repr(end_s)
        + ', "narration": "Tramo trazable"}]}'
    )


class StubSession:
    """Sesión falsa: registra llamadas y sirve texto programado."""

    def __init__(
        self,
        text: str | None = VALID_JSON,
        *,
        error: Exception | None = None,
        before_return: Callable[[], None] | None = None,
    ) -> None:
        self.calls: list[tuple[str, type]] = []
        self._text = text
        self._error = error
        self._before_return = before_return

    def generate(self, prompt: str, response_schema: type) -> str:
        self.calls.append((prompt, response_schema))
        if self._before_return is not None:
            self._before_return()
        if self._error is not None:
            raise self._error
        if self._text is None:
            raise GeminiInvalidResponseError("respuesta vacía programada")
        return self._text


def make_client(
    session: StubSession,
    config: GeminiClientConfig | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[RealGeminiScriptPort, list[GeminiClientConfig]]:
    """Cliente con sesión inyectada; registra las configs recibidas."""
    received: list[GeminiClientConfig] = []

    def factory(cfg: GeminiClientConfig) -> StubSession:
        received.append(cfg)
        return session

    port = RealGeminiScriptPort(
        config or GeminiClientConfig(api_key="clave-falsa"),
        session_factory=factory,
        cancel_event=cancel_event,
    )
    return port, received


# --- disponibilidad y cancelación ---------------------------------------------


def test_cliente_cumple_el_puerto() -> None:
    port, _ = make_client(StubSession())

    assert isinstance(port, GeminiScriptPort)


def test_sin_credenciales_falla_de_forma_controlada() -> None:
    port = RealGeminiScriptPort(GeminiClientConfig(api_key=None))

    with pytest.raises(GeminiNotAvailableError, match="credencial"):
        port.propose_script(make_request())


def test_cancelacion_previa_no_llama_a_la_sesion() -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    session = StubSession()
    port, _ = make_client(session, cancel_event=cancel_event)

    with pytest.raises(GeminiCancelledError):
        port.propose_script(make_request())

    assert session.calls == []


def test_cancelacion_durante_la_llamada_gana_al_resultado() -> None:
    cancel_event = threading.Event()
    session = StubSession(before_return=cancel_event.set)
    port, _ = make_client(session, cancel_event=cancel_event)

    with pytest.raises(GeminiCancelledError):
        port.propose_script(make_request())


def test_cancel_metodo_solicita_parada() -> None:
    session = StubSession()
    port, _ = make_client(session)

    port.cancel()

    with pytest.raises(GeminiCancelledError):
        port.propose_script(make_request())


# --- generación ---------------------------------------------------------------


def test_propuesta_trazable_con_material_valido() -> None:
    session = StubSession(text=VALID_JSON)
    port, received = make_client(session)

    proposal = port.propose_script(make_request())

    assert isinstance(proposal, ScriptProposal)
    assert proposal.source_id == "src-1"
    assert proposal.requested_duration_s == pytest.approx(10.0)
    assert proposal.entries[0].start_s == pytest.approx(0.0)
    assert proposal.entries[0].end_s == pytest.approx(10.0)
    assert proposal.entries[0].narration == "Locución inicial"
    assert proposal.total_duration_s == pytest.approx(10.0)
    prompt, schema = session.calls[0]
    assert "src-1" in prompt
    assert schema.__name__ == "ScriptPayload"
    assert received and received[0].api_key is not None


def test_entradas_desordenadas_se_devuelven_ordenadas() -> None:
    port, _ = make_client(StubSession(text=UNSORTED_JSON))

    proposal = port.propose_script(make_request())

    assert [entry.start_s for entry in proposal.entries] == [0.0, 5.0]


def test_la_sesion_se_reutiliza_entre_peticiones() -> None:
    session = StubSession()
    port, received = make_client(session)

    port.propose_script(make_request())
    port.propose_script(make_request())

    assert len(session.calls) == 2
    assert len(received) == 1


def test_prompt_incluye_duracion_pedida_y_segmentos() -> None:
    session = StubSession(text=make_window_json(0.0, 7.0))
    port, _ = make_client(session)

    port.propose_script(make_request(requested=7.0))

    prompt, _ = session.calls[0]
    assert "7.0" in prompt
    assert "10.0" in prompt


# --- validación sin confianza ciega --------------------------------------------


def test_segmento_inventado_se_rechaza() -> None:
    port, _ = make_client(StubSession(text=INVENTED_JSON))

    with pytest.raises(InventedSegmentError, match=r"inventar|inexistente"):
        port.propose_script(make_request())


def test_material_insuficiente_se_declara() -> None:
    port, _ = make_client(StubSession(text=INSUFFICIENT_JSON))

    with pytest.raises(InsufficientMaterialError, match="insuficiente"):
        port.propose_script(make_request())


def test_respuesta_no_json_se_rechaza() -> None:
    port, _ = make_client(StubSession(text="no soy json"))

    with pytest.raises(GeminiInvalidResponseError):
        port.propose_script(make_request())


def test_respuesta_vacia_invalida_no_se_traga() -> None:
    port, _ = make_client(StubSession(text=None))

    with pytest.raises(GeminiInvalidResponseError):
        port.propose_script(make_request())


# --- errores tipados y plazo ----------------------------------------------------


def test_error_de_cuota_se_propaga_tipado() -> None:
    port, _ = make_client(StubSession(error=GeminiQuotaExceededError("429")))

    with pytest.raises(GeminiQuotaExceededError):
        port.propose_script(make_request())


def test_error_de_peticion_se_propaga_tipado() -> None:
    port, _ = make_client(StubSession(error=GeminiRequestError("red")))

    with pytest.raises(GeminiRequestError):
        port.propose_script(make_request())


def test_plazo_excedido_se_tipa_como_timeout() -> None:
    session = StubSession(before_return=lambda: time.sleep(0.4))
    config = GeminiClientConfig(api_key="clave-falsa", timeout_s=0.1)
    port, _ = make_client(session, config=config)

    with pytest.raises(GeminiTimeoutError, match="plazo"):
        port.propose_script(make_request())
