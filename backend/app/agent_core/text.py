from __future__ import annotations

import unicodedata


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    unaccented = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return unaccented.replace("đ", "d").replace("Đ", "D")
