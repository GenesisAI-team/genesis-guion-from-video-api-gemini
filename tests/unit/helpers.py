"""Factorías compartidas para tests del puerto Gemini y su cliente (GEN-45)."""

from __future__ import annotations

from pathlib import Path

from genesis_video_ai.gemini.port import ScriptEntry, ScriptProposal, ScriptProposalRequest
from genesis_video_ai.models.contracts import Segment, SourceMedia


def make_source(duration_s: float = 42.5, source_id: str = "src-1") -> SourceMedia:
    """Factoría de la fuente original que se enviaría al puerto."""
    return SourceMedia(
        id=source_id,
        path=Path("C:/medias/original.mp4"),
        container="mp4",
        duration_s=duration_s,
        size_bytes=4242,
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
    )


def make_segment(source_id: str = "src-1", start_s: float = 0.0, end_s: float = 10.0) -> Segment:
    """Factoría de un segmento medido del original."""
    return Segment(source_id=source_id, start_s=start_s, end_s=end_s)


def make_request(requested: float = 10.0) -> ScriptProposalRequest:
    """Petición de ejemplo para el puerto."""
    return ScriptProposalRequest(
        source=make_source(),
        segments=(make_segment(),),
        requested_duration_s=requested,
    )


def make_entry(
    source_id: str = "src-1",
    start_s: float = 0.0,
    end_s: float = 8.5,
    narration: str = "Locución sobre el material original.",
    justification: str = "",
) -> ScriptEntry:
    """Factoría de una entrada de guion trazable."""
    return ScriptEntry(
        source_id=source_id,
        start_s=start_s,
        end_s=end_s,
        narration=narration,
        justification=justification,
    )


def make_proposal(requested: float = 8.5) -> ScriptProposal:
    """Factoría de una propuesta trazable coherente con la duración pedida."""
    return ScriptProposal(
        source_id="src-1",
        requested_duration_s=requested,
        entries=(make_entry(end_s=requested),),
    )
