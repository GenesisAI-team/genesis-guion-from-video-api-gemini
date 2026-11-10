"""Tests del parseo estructurado de la salida del modelo (GEN-45).

Sin confianza ciega: el texto devuelto por el modelo solo entra al sistema
si es JSON válido que cumple el esquema estricto de la propuesta.
"""

from __future__ import annotations

import pytest

from genesis_video_ai.gemini.errors import GeminiInvalidResponseError
from genesis_video_ai.gemini.response import ScriptPayload, parse_payload

VALID_JSON = """
{
  "entries": [
    {"start_s": 0.0, "end_s": 8.5,
     "narration": "Apertura sobre el material.",
     "justification": "Tramo inicial medido"}
  ]
}
"""


def test_json_valido_se_parsea_como_payload() -> None:
    payload = parse_payload(VALID_JSON)

    assert len(payload.entries) == 1
    assert payload.entries[0].start_s == pytest.approx(0.0)
    assert payload.entries[0].end_s == pytest.approx(8.5)
    assert payload.entries[0].narration.startswith("Apertura")


def test_payload_vacio_es_parseable_para_declarar_insuficiencia() -> None:
    payload = parse_payload('{"entries": []}')

    assert payload.entries == ()


def test_json_invalido_se_rechaza_con_error_tipado() -> None:
    with pytest.raises(GeminiInvalidResponseError, match="JSON"):
        parse_payload("esto no es json {")


def test_json_que_no_es_objeto_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError):
        parse_payload("[1, 2, 3]")


def test_entrada_con_campo_faltante_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError, match="end_s"):
        parse_payload('{"entries": [{"start_s": 0.0, "narration": "texto"}]}')


def test_entrada_con_campo_extra_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError, match="extra"):
        parse_payload(
            '{"entries": [{"start_s": 0.0, "end_s": 5.0, "narration": "t",'
            ' "material": "inventado"}]}'
        )


def test_entrada_con_tiempo_incoherente_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError):
        parse_payload('{"entries": [{"start_s": 5.0, "end_s": 5.0, "narration": "t"}]}')


def test_entrada_con_tiempo_negativo_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError):
        parse_payload('{"entries": [{"start_s": -1.0, "end_s": 5.0, "narration": "t"}]}')


def test_entrada_con_narracion_en_blanco_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError, match="narration"):
        parse_payload('{"entries": [{"start_s": 0.0, "end_s": 5.0, "narration": "  "}]}')

    with pytest.raises(GeminiInvalidResponseError):
        parse_payload('{"entries": [{"start_s": 0.0, "end_s": 5.0}]}')


def test_entrada_con_tiempo_no_finito_se_rechaza() -> None:
    """json.loads acepta NaN/Infinity no estándar; el esquema no debe permitirlos."""
    with pytest.raises(GeminiInvalidResponseError):
        parse_payload('{"entries": [{"start_s": NaN, "end_s": 5.0, "narration": "t"}]}')

    with pytest.raises(GeminiInvalidResponseError):
        parse_payload('{"entries": [{"start_s": 0.0, "end_s": Infinity, "narration": "t"}]}')


def test_texto_no_str_se_rechaza() -> None:
    with pytest.raises(GeminiInvalidResponseError):
        parse_payload(None)  # type: ignore[arg-type]


def test_el_esquema_se_expone_para_el_sdk() -> None:
    """El modelo pydantic se pasa al SDK como response_schema."""
    assert ScriptPayload.model_json_schema()["type"] == "object"
