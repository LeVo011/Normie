from __future__ import annotations

import re

from app.models import InputKind


CREATE_TABLE_PATTERN = re.compile(r"\bcreate\s+table\b", re.IGNORECASE)


def detect_input_kind(text: str) -> InputKind:
    """Classify input without asking an LLM."""
    return InputKind.SQL_DDL if CREATE_TABLE_PATTERN.search(text) else InputKind.FREE_TEXT
