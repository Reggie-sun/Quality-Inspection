from __future__ import annotations

import re
from pathlib import Path


ILLEGAL_FILE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ILLEGAL_SHEET = re.compile(r"[\\/*?:\[\]]")


def safe_stem(value: str, fallback: str = "inspection") -> str:
    stem = Path(value).name.rsplit(".", 1)[0]
    stem = ILLEGAL_FILE.sub("_", stem).strip(" .")
    return (stem or fallback)[:120]


def unique_sheet_name(value: str, used: set[str]) -> str:
    base = ILLEGAL_SHEET.sub("_", value).strip("'") or "Sheet"
    base = base[:31].rstrip("'") or "Sheet"
    candidate = base
    suffix = 2
    used_casefold = {name.casefold() for name in used}
    while candidate.casefold() in used_casefold:
        marker = f"_{suffix}"
        candidate = f"{base[: 31 - len(marker)]}{marker}"
        suffix += 1
    used.add(candidate)
    return candidate
