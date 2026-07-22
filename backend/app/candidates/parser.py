from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from app.candidates.schemas import Candidate, stable_candidate_id


NUMBER = r"[0-9]+(?:\.[0-9]+)?"
DEVIATION = rf"(?:[+-]{NUMBER}|0(?:\.0+)?)"
QUANTITY = re.compile(
    rf"^(?P<quantity>[1-9][0-9]*)\s*(?P<separator>[×xX-])\s*(?P<body>.+)$"
)
THREAD = re.compile(
    rf"^(?P<spec>M{NUMBER}(?:\s*[×xX]\s*{NUMBER})?)"
    rf"(?:\s*(?:深|↓)\s*(?P<depth>{NUMBER}))?"
    r"(?:\s*(?P<through>通|贯穿))?$"
)
DIAMETER = re.compile(
    rf"^Φ\s*(?P<nominal>{NUMBER})"
    rf"(?:\s*(?:深|↓)\s*(?P<depth>{NUMBER}))?"
    r"(?:\s*(?P<through>通|贯穿))?$"
)
RADIUS = re.compile(rf"^R\s*(?P<value>{NUMBER})$")
LINEAR_TOLERANCE = (
    rf"(?:\s*±\s*(?P<symmetric>{NUMBER})"
    rf"|\s*(?P<upper>{DEVIATION})\s*/\s*(?P<lower>{DEVIATION}))"
)
ANGLE_TOLERANCE = rf"(?:\s*±\s*(?P<symmetric>{NUMBER})\s*°?)"
ANGLE = re.compile(rf"^(?P<value>{NUMBER})\s*°(?:{ANGLE_TOLERANCE})?$")
LINEAR = re.compile(rf"^(?P<value>{NUMBER})(?:{LINEAR_TOLERANCE})?$")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for symbol in ("∅", "ø", "⌀"):
        normalized = normalized.replace(symbol, "Φ")
    return " ".join(normalized.split())


def _tolerances(match: re.Match[str]) -> tuple[Decimal | None, Decimal | None]:
    groups = match.groupdict()
    if symmetric := groups.get("symmetric"):
        value = Decimal(symmetric)
        return value, -value
    upper = groups.get("upper")
    lower = groups.get("lower")
    if upper is not None and lower is not None:
        return Decimal(upper), Decimal(lower)
    return None, None


def _canonical_thread_spec(spec: str) -> str:
    return re.sub(r"\s*[xX×]\s*", "×", spec)


def parse_annotation(raw_text: str) -> Candidate:
    normalized = normalize_text(raw_text)
    quantity: int | None = None
    if quantity_match := QUANTITY.fullmatch(normalized):
        body = quantity_match.group("body")
        if quantity_match.group("separator") != "-" or not body[0].isdigit():
            quantity = int(quantity_match.group("quantity"))
            normalized = body

    common = {
        "candidate_id": stable_candidate_id("annotation", raw_text),
        "raw_text": raw_text,
        "normalized_text": normalized,
        "quantity": quantity,
    }
    if match := THREAD.fullmatch(normalized):
        return Candidate(
            **common,
            item_type="thread",
            thread_spec=_canonical_thread_spec(match.group("spec")),
            thread_depth=(
                Decimal(match.group("depth")) if match.group("depth") else None
            ),
            through=match.group("through") is not None,
        )
    if match := DIAMETER.fullmatch(normalized):
        return Candidate(
            **common,
            item_type="diameter_dimension",
            nominal=Decimal(match.group("nominal")),
            feature_kind="unknown",
            depth=Decimal(match.group("depth")) if match.group("depth") else None,
            through=match.group("through") is not None,
            requires_confirmation=True,
        )
    if match := RADIUS.fullmatch(normalized):
        return Candidate(
            **common,
            item_type="radius",
            radius_value=Decimal(match.group("value")),
        )
    if match := ANGLE.fullmatch(normalized):
        upper, lower = _tolerances(match)
        return Candidate(
            **common,
            item_type="angle",
            angle_value=Decimal(match.group("value")),
            upper_tolerance=upper,
            lower_tolerance=lower,
        )
    if match := LINEAR.fullmatch(normalized):
        upper, lower = _tolerances(match)
        return Candidate(
            **common,
            item_type="linear_dimension",
            nominal=Decimal(match.group("value")),
            upper_tolerance=upper,
            lower_tolerance=lower,
        )
    raise ValueError(f"unsupported deterministic annotation: {raw_text}")
