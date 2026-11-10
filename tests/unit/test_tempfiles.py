"""Tests de los temporales de sesión (GEN-36 §2)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from genesis_video_ai.jobs.tempfiles import SESSION_TEMP_PREFIX, session_temp_dir


def test_prefijo_de_sesion_estable() -> None:
    """El prefijo es estable para localizar los temporales de la sesión."""
    assert SESSION_TEMP_PREFIX == "genesis-video-ai-"


def test_temporal_de_sesion_crea_directorio_con_prefijo(tmp_path: Path) -> None:
    with session_temp_dir(root=tmp_path) as temp_root:
        assert temp_root.is_dir()
        assert temp_root.name.startswith("genesis-video-ai-")
        assert temp_root.parent == tmp_path


def test_el_contenido_se_elimina_al_salir(tmp_path: Path) -> None:
    with session_temp_dir(root=tmp_path) as temp_root:
        scratch = temp_root / "analisis.json"
        scratch.write_text("{}", encoding="utf-8")
        assert scratch.exists()

    assert not temp_root.exists()


def test_el_contenido_se_elimina_aun_con_excepcion(tmp_path: Path) -> None:
    with (
        pytest.raises(RuntimeError, match="falla"),
        session_temp_dir(root=tmp_path) as temp_root,
    ):
        (temp_root / "parcial.json").write_text("{}", encoding="utf-8")
        raise RuntimeError("falla en el flujo")

    assert not temp_root.exists()


def test_limpieza_perdona_directorio_borrado_dentro(tmp_path: Path) -> None:
    with session_temp_dir(root=tmp_path) as temp_root:
        shutil.rmtree(temp_root)

    assert not temp_root.exists()


def test_prefijo_y_raiz_personalizables(tmp_path: Path) -> None:
    with session_temp_dir(prefix="gen-testing-", root=tmp_path) as temp_root:
        assert temp_root.parent == tmp_path
        assert temp_root.name.startswith("gen-testing-")
        assert temp_root.is_dir()

    assert not temp_root.exists()
