from __future__ import annotations


def unit_id(class_level: str, chapter_no: int, serial: int) -> str:
    return f"PHY{int(class_level):02d}_CH{int(chapter_no):02d}_U{serial:03d}"


def record_id(prefix: str, source_unit_id: str, serial: int) -> str:
    return f"{prefix}_{source_unit_id}_{serial:03d}"


def card_id(prefix: str, source_unit_id: str, serial: int) -> str:
    return f"{prefix}_{source_unit_id}_{serial:03d}"


def chunk_id(source_unit_id: str, serial: int) -> str:
    return f"RAG_{source_unit_id}_{serial:03d}"
