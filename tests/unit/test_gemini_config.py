"""Tests de la configuración del cliente Gemini (GEN-45)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from genesis_video_ai.gemini.config import GeminiClientConfig


def test_config_por_defecto_sin_credenciales() -> None:
    config = GeminiClientConfig()

    assert config.model == "gemini-2.5-flash"
    assert config.timeout_s == pytest.approx(120.0)
    assert config.tolerance_s == pytest.approx(0.05)
    assert config.max_output_tokens is None
    assert config.temperature is None
    assert config.api_key is None


def test_config_acepta_valores_personalizados() -> None:
    config = GeminiClientConfig(
        model="gemini-2.5-pro",
        timeout_s=30.0,
        max_output_tokens=2048,
        temperature=0.0,
        tolerance_s=0.2,
        api_key="secreto",
    )

    assert config.model == "gemini-2.5-pro"
    assert config.timeout_s == pytest.approx(30.0)
    assert config.max_output_tokens == 2048
    assert config.temperature == pytest.approx(0.0)
    assert config.tolerance_s == pytest.approx(0.2)
    assert config.api_key is not None


def test_config_no_filtrra_la_clave_en_su_repr() -> None:
    config = GeminiClientConfig(api_key="secreto-super-privado")

    assert "secreto-super-privado" not in repr(config)
    assert "secreto-super-privado" not in str(config)


def test_config_rechaza_timeout_invalido() -> None:
    with pytest.raises(ValidationError, match="timeout_s"):
        GeminiClientConfig(timeout_s=0.0)


def test_config_rechaza_timeout_infinito() -> None:
    with pytest.raises(ValidationError):
        GeminiClientConfig(timeout_s=math.inf)


def test_config_rechaza_temperatura_fuera_de_rango() -> None:
    with pytest.raises(ValidationError, match="temperature"):
        GeminiClientConfig(temperature=3.0)


def test_config_rechaza_tolencia_negativa() -> None:
    with pytest.raises(ValidationError, match="tolerance_s"):
        GeminiClientConfig(tolerance_s=-0.1)


def test_config_rechaza_modelo_vacio() -> None:
    with pytest.raises(ValidationError, match="model"):
        GeminiClientConfig(model="")


def test_config_rechaza_campos_extra() -> None:
    with pytest.raises(ValidationError):
        GeminiClientConfig(api_key_file="secrets.txt")  # type: ignore[call-arg]


def test_from_env_lee_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    config = GeminiClientConfig.from_env()

    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "clave-de-prueba"


def test_from_env_usa_google_api_key_como_alternativa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "clave-alternativa")

    config = GeminiClientConfig.from_env()

    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "clave-alternativa"


def test_from_env_sin_claves_devuelve_config_sin_credencial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    config = GeminiClientConfig.from_env()

    assert config.api_key is None
