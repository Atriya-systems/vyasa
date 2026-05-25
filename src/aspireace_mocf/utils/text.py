from __future__ import annotations

import re
from typing import Any


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"([A-Za-z])-\s*\n\s*([A-Za-z])", r"\1\2", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\bL\s*T\s*-\s*1\b", "[LT^-1]", text)
    text = re.sub(r"\bM\s*L\s*T\s*-\s*2\b", "[MLT^-2]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_source_id(data: Any) -> str:
    if isinstance(data, dict) and data.get("source_id"):
        return str(data["source_id"])
    return "UNKNOWN_SOURCE"


def extract_owned_text(data: Any) -> str:
    if isinstance(data, dict):
        if "owned_sme_text" in data:
            return normalize_text(str(data["owned_sme_text"]))
        if "text" in data:
            return normalize_text(str(data["text"]))
        if "pages" in data and isinstance(data["pages"], list):
            return normalize_text(" ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in data["pages"]))
        return normalize_text(" ".join(str(v) for v in data.values() if isinstance(v, str)))
    if isinstance(data, list):
        return normalize_text(" ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in data))
    return normalize_text(str(data))
