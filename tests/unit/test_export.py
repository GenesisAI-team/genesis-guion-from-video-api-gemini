"""Exportación de guiones a JSON y Markdown (GEN-50).

Las exportaciones son verificables: siempre referencian el original medido
(ruta absoluta, contenedor, duración real) y los tiempos in/out reales de
cada tramo. Nada se calcula aparte: la duración total sale de las entradas.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from genesis_video_ai.gemini.port import ScriptEntry, ScriptProposal
from genesis_video_ai.jobs.export import export_proposal_json, export_proposal_markdown
from genesis_video_ai.models.contracts import SourceMedia

_RUTA_ORIGINAL = Path("C:/videos/original.mp4").resolve()


def fuente(id: str = "src-1") -> SourceMedia:
    """Original medido de ejemplo."""
    return SourceMedia(
        id=id,
        path=_RUTA_ORIGINAL,
        container="mp4",
        duration_s=120.0,
        size_bytes=4242,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def fuente_en(ruta: Path) -> SourceMedia:
    """Original medido cuyo fichero existe en la ruta dada."""
    return SourceMedia(
        id="src-1",
        path=ruta.resolve(),
        container="mp4",
        duration_s=120.0,
        size_bytes=ruta.stat().st_size,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def propuesta() -> ScriptProposal:
    """Guion trazable de ejemplo con dos tramos reales."""
    return ScriptProposal(
        source_id="src-1",
        requested_duration_s=90.0,
        entries=(
            ScriptEntry(
                source_id="src-1",
                start_s=0.0,
                end_s=45.0,
                narration="Apertura con material real grabado.",
                justification="Primer bloque medido",
            ),
            ScriptEntry(
                source_id="src-1",
                start_s=60.0,
                end_s=105.0,
                narration="Cierre con locución en acento: montaje final.",
                justification="Segundo bloque medido",
            ),
        ),
    )


class TestExportJson:
    def test_guarda_fuente_y_tiempos_reales(self, tmp_path: Path) -> None:
        destino = tmp_path / "guion.json"

        ruta = export_proposal_json(propuesta(), fuente(), destino)

        assert ruta == destino
        assert destino.exists()
        payload = json.loads(destino.read_text(encoding="utf-8"))
        assert payload["source"]["id"] == "src-1"
        assert payload["source"]["path"] == str(_RUTA_ORIGINAL)
        assert payload["source"]["container"] == "mp4"
        assert payload["source"]["duration_s"] == pytest.approx(120.0)
        assert payload["requested_duration_s"] == pytest.approx(90.0)
        assert payload["total_duration_s"] == pytest.approx(90.0)
        assert len(payload["entries"]) == 2
        assert payload["entries"][0]["start_s"] == pytest.approx(0.0)
        assert payload["entries"][0]["end_s"] == pytest.approx(45.0)
        assert payload["entries"][0]["duration_s"] == pytest.approx(45.0)
        assert payload["entries"][0]["narration"] == "Apertura con material real grabado."
        assert payload["entries"][0]["justification"] == "Primer bloque medido"
        assert payload["entries"][1]["start_s"] == pytest.approx(60.0)
        assert payload["entries"][1]["end_s"] == pytest.approx(105.0)
        assert payload["entries"][1]["source_id"] == "src-1"

    def test_rechaza_una_propuesta_de_otro_original(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="src-1"):
            export_proposal_json(propuesta(), fuente(id="src-2"), tmp_path / "guion.json")
        assert not (tmp_path / "guion.json").exists()

    def test_crea_el_directorio_de_destino(self, tmp_path: Path) -> None:
        destino = tmp_path / "export" / "guion.json"

        export_proposal_json(propuesta(), fuente(), destino)

        assert destino.exists()


class TestExportMarkdown:
    def test_tabla_con_fuente_y_tiempos_reales(self, tmp_path: Path) -> None:
        destino = tmp_path / "guion.md"

        ruta = export_proposal_markdown(propuesta(), fuente(), destino)

        assert ruta == destino
        texto = destino.read_text(encoding="utf-8")
        assert "# Guion propuesto" in texto
        assert f"`{_RUTA_ORIGINAL}`" in texto
        assert "mp4" in texto
        assert "Duración real del original: 120 s" in texto
        assert "Duración pedida: 90 s" in texto
        assert "Duración total calculada: 90 s" in texto
        assert "| # | Entrada (s) | Salida (s) | Duración (s) | Narración |" in texto
        assert "| 1 | 0 | 45 | 45 |" in texto
        assert "| 2 | 60 | 105 | 45 |" in texto
        assert "Apertura con material real grabado." in texto
        assert "Primer bloque medido" in texto
        assert "Segundo bloque medido" in texto

    def test_rechaza_una_propuesta_de_otro_original(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="src-2"):
            export_proposal_markdown(propuesta(), fuente(id="src-2"), tmp_path / "guion.md")

    def test_crea_el_directorio_de_destino(self, tmp_path: Path) -> None:
        destino = tmp_path / "salidas" / "guion.md"

        export_proposal_markdown(propuesta(), fuente(), destino)

        assert destino.exists()


class TestElDestinoNoDebeSerElOriginal:
    """La exportación nunca abre para escritura el original ni sus enlaces."""

    def test_json_rechaza_escribir_sobre_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")

        with pytest.raises(ValueError, match="material original"):
            export_proposal_json(propuesta(), fuente_en(original), original)

        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_markdown_rechaza_escribir_sobre_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")

        with pytest.raises(ValueError, match="material original"):
            export_proposal_markdown(propuesta(), fuente_en(original), original)

        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_json_rechaza_un_symlink_hacia_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")
        enlace = tmp_path / "atajo.mp4"
        try:
            enlace.symlink_to(original)
        except OSError as exc:
            pytest.skip(f"no se pueden crear symlinks aquí: {exc}")

        with pytest.raises(ValueError, match="material original"):
            export_proposal_json(propuesta(), fuente_en(original), enlace)

        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_markdown_rechaza_un_symlink_hacia_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")
        enlace = tmp_path / "atajo.md"
        try:
            enlace.symlink_to(original)
        except OSError as exc:
            pytest.skip(f"no se pueden crear symlinks aquí: {exc}")

        with pytest.raises(ValueError, match="material original"):
            export_proposal_markdown(propuesta(), fuente_en(original), enlace)

        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_json_rechaza_un_enlace_duro_hacia_el_original(self, tmp_path: Path) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")
        enlace_duro = tmp_path / "copia.mp4"
        os.link(original, enlace_duro)

        with pytest.raises(ValueError, match="material original"):
            export_proposal_json(propuesta(), fuente_en(original), enlace_duro)

        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_json_exporta_normal_a_un_destino_distinto_del_original(
        self,
        tmp_path: Path,
    ) -> None:
        original = tmp_path / "original.mp4"
        original.write_bytes(b"MATERIAL AUDIOVISUAL")
        destino = tmp_path / "guion.json"

        ruta = export_proposal_json(propuesta(), fuente_en(original), destino)

        assert ruta == destino
        payload = json.loads(destino.read_text(encoding="utf-8"))
        assert payload["source"]["path"] == str(original.resolve())
        assert original.read_bytes() == b"MATERIAL AUDIOVISUAL"

    def test_json_reemplaza_un_destino_previo_sin_original_en_disco(
        self,
        tmp_path: Path,
    ) -> None:
        destino = tmp_path / "guion.json"
        destino.write_text("contenido previo")

        export_proposal_json(propuesta(), fuente(), destino)

        payload = json.loads(destino.read_text(encoding="utf-8"))
        assert payload["source"]["id"] == "src-1"
