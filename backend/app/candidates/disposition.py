from __future__ import annotations

import re

from app.candidates.parser import normalize_text
from app.candidates.schemas import Candidate, stable_candidate_id


INSPECTION_VERB = re.compile(r"检查|检验|检测|测量|确认|验证")
VERIFIABLE_CRITERION = re.compile(
    r"不得|不允许|应为|应达到|应符合|符合|不大于|不小于|≤|≥|无(?:毛刺|裂纹|缺陷|损伤)"
)


def classify_technical_requirement(
    raw_text: str,
    coordinates: tuple[float, float, float, float] | None = None,
    *,
    source_id: str,
) -> Candidate | None:
    source_identity = source_id.strip()
    if not source_identity:
        raise ValueError("source_id must be non-blank")
    normalized = normalize_text(raw_text)
    if not INSPECTION_VERB.search(normalized):
        return None
    if not VERIFIABLE_CRITERION.search(normalized):
        return None
    return Candidate(
        candidate_id=stable_candidate_id(
            "general-requirement",
            source_identity,
            raw_text,
        ),
        item_type="general_requirement",
        raw_text=raw_text,
        normalized_text=normalized,
        coordinates=coordinates,
        scope="global_requirement",
        balloon_required=False,
    )
