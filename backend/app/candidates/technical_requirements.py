from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.candidates.parser import normalize_text
from app.candidates.schemas import stable_candidate_id
from app.pdf.schemas import TextObservation


TECHNICAL_REQUIREMENT_RULE_VERSION = "technical-requirement/1"

RequirementCategory = Literal[
    "standalone_check",
    "applicability_rule",
    "unsupported",
    "ambiguous",
]
RequirementSubtype = Literal[
    "deburr",
    "surface_integrity",
    "surface_treatment",
    "default_chamfer",
    "general_dimensional_tolerance",
    "general_geometric_tolerance",
    "unsupported",
    "ambiguous",
]
MatchOutcome = Literal["matched_items", "global_scope", "unresolved"]

_HEADING = re.compile(r"^技术要求\s*[:：]?$")
_NUMBERED_ENTRY = re.compile(r"^(?P<ordinal>[1-9][0-9]*)\s*[.．、)]\s*(?P<body>.+)$")
_DIMENSIONAL_STANDARD = re.compile(
    r"未(?:注|标注)尺寸公差按\s*GB\s*/\s*T\s*1804\s*[-—]?\s*"
    r"(?P<class>[FfMmCcVv])\s*执行"
)
_GEOMETRIC_STANDARD = re.compile(
    r"未(?:注|标注)形位公差按\s*GB\s*/\s*T\s*1184\s*[-—]?\s*"
    r"(?P<class>[HhKkLl])\s*执行"
)
_UNKNOWN_DIMENSIONAL_STANDARD = re.compile(r"未(?:注|标注)尺寸公差按.+执行")
_UNKNOWN_GEOMETRIC_STANDARD = re.compile(r"未(?:注|标注)形位公差按.+执行")
_DEFAULT_CHAMFER = re.compile(
    r"未(?:注|标注)(?:的)?倒角\s*C\s*(?P<size>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_DEBURR = re.compile(r"(?:锐边.*?(?:去除?|清除)毛刺|去除?毛刺)")
_SURFACE_INTEGRITY = re.compile(
    r"表面.*?(?:划痕|擦伤|损伤).*?(?:缺陷|外观)"
)
_SURFACE_TREATMENT = re.compile(r"表面.*?阳极氧化.*?处理")


@dataclass(frozen=True)
class TechnicalRequirementEntry:
    ordinal: int | None
    raw_text: str
    normalized_text: str
    source_location_ids: tuple[str, ...]
    source_segment_ids: tuple[str, ...]
    page_index: int
    coordinates: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True)
class _ObservationSegment:
    observation: TextObservation
    index: int
    text: str
    bbox_pdf: tuple[float, float, float, float]

    @property
    def segment_id(self) -> str:
        return f"{self.observation.observation_id}#{self.index}"


@dataclass(frozen=True)
class _Classification:
    category: RequirementCategory
    subtype: RequirementSubtype
    parsed_parameters: dict[str, str]
    inspection_item: str | None
    inspection_standard: str | None
    key_dimension: str | None


class SipSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspection_item: str | None = None
    inspection_standard: str | None = None
    key_dimension: str | None = None
    source_page: int = Field(ge=1)
    remarks: str


class TechnicalRequirementDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1)
    ordinal: int | None = Field(default=None, ge=1)
    raw_text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    source_location_ids: list[str] = Field(min_length=1)
    page_index: int = Field(ge=0)
    coordinates: list[tuple[float, float, float, float]] = Field(min_length=1)
    category: RequirementCategory
    subtype: RequirementSubtype
    parsed_parameters: dict[str, str]
    match_outcome: MatchOutcome
    matched_candidate_ids: list[str]
    generated_candidate_id: str | None = None
    rule_id: str = Field(min_length=1)
    rule_version: Literal["technical-requirement/1"]
    review_required: bool
    sip_suggestion: SipSuggestion


def _segments(
    observations: Sequence[TextObservation],
) -> tuple[_ObservationSegment, ...]:
    segments: list[_ObservationSegment] = []
    for observation in observations:
        raw_segments = observation.raw_text.splitlines() or [observation.raw_text]
        segment_count = max(len(raw_segments), 1)
        x0, y0, x1, y1 = observation.bbox_pdf
        segment_height = (y1 - y0) / segment_count
        for index, raw_segment in enumerate(raw_segments):
            text = raw_segment.strip()
            if not text:
                continue
            segment_y0 = y0 + segment_height * index
            segments.append(
                _ObservationSegment(
                    observation=observation,
                    index=index,
                    text=text,
                    bbox_pdf=(
                        x0,
                        segment_y0,
                        x1,
                        segment_y0 + segment_height,
                    ),
                )
            )
    return tuple(segments)


def _same_direction(
    first: tuple[float, float],
    second: tuple[float, float],
) -> bool:
    return abs(first[0] - second[0]) <= 0.05 and abs(first[1] - second[1]) <= 0.05


def _can_continue(
    previous: _ObservationSegment,
    current: _ObservationSegment,
) -> bool:
    if previous.observation.page_index != current.observation.page_index:
        return False
    if not _same_direction(
        previous.observation.direction,
        current.observation.direction,
    ):
        return False
    previous_height = max(previous.bbox_pdf[3] - previous.bbox_pdf[1], 1.0)
    vertical_gap = current.bbox_pdf[1] - previous.bbox_pdf[3]
    return -1.0 <= vertical_gap <= max(4.0, previous_height * 0.75)


def _join_requirement_text(parts: Sequence[str]) -> str:
    combined = ""
    for part in parts:
        if (
            combined
            and combined[-1].isascii()
            and combined[-1].isalnum()
            and part[0].isascii()
            and part[0].isalnum()
        ):
            combined += " "
        combined += part
    return combined


def _entry_from_segments(
    ordinal: int,
    segments: Sequence[_ObservationSegment],
    texts: Sequence[str],
) -> TechnicalRequirementEntry:
    source_location_ids = tuple(
        dict.fromkeys(segment.observation.observation_id for segment in segments)
    )
    raw_text = _join_requirement_text(texts)
    return TechnicalRequirementEntry(
        ordinal=ordinal,
        raw_text=raw_text,
        normalized_text=normalize_text(raw_text),
        source_location_ids=source_location_ids,
        source_segment_ids=tuple(segment.segment_id for segment in segments),
        page_index=segments[0].observation.page_index,
        coordinates=tuple(segment.bbox_pdf for segment in segments),
    )


def reconstruct_technical_requirement_entries(
    observations: Sequence[TextObservation],
) -> tuple[TechnicalRequirementEntry, ...]:
    entries: list[TechnicalRequirementEntry] = []
    active_block = False
    awaiting_first_entry = False
    current_ordinal: int | None = None
    current_segments: list[_ObservationSegment] = []
    current_texts: list[str] = []

    def flush() -> None:
        nonlocal current_ordinal, current_segments, current_texts
        if current_ordinal is not None and current_segments:
            entries.append(
                _entry_from_segments(
                    current_ordinal,
                    current_segments,
                    current_texts,
                )
            )
        current_ordinal = None
        current_segments = []
        current_texts = []

    for segment in _segments(observations):
        normalized_segment = normalize_text(segment.text)
        if _HEADING.fullmatch(normalized_segment):
            flush()
            active_block = True
            awaiting_first_entry = True
            continue
        if not active_block:
            continue

        numbered = _NUMBERED_ENTRY.fullmatch(normalized_segment)
        if numbered is not None:
            flush()
            current_ordinal = int(numbered.group("ordinal"))
            current_segments = [segment]
            current_texts = [numbered.group("body").strip()]
            awaiting_first_entry = False
            continue

        if awaiting_first_entry or not current_segments:
            active_block = False
            awaiting_first_entry = False
            continue
        if not _can_continue(current_segments[-1], segment):
            flush()
            active_block = False
            continue
        current_segments.append(segment)
        current_texts.append(segment.text)

    flush()
    return tuple(entries)


def classify_general_dimensional_tolerance(
    text: str,
) -> _Classification | None:
    match = _DIMENSIONAL_STANDARD.search(text)
    if match is None:
        return None
    tolerance_class = match.group("class").lower()
    return _Classification(
        category="applicability_rule",
        subtype="general_dimensional_tolerance",
        parsed_parameters={
            "standard_code": "GB/T 1804",
            "tolerance_class": tolerance_class,
        },
        inspection_item="未注尺寸公差",
        inspection_standard=f"GB/T 1804-{tolerance_class}",
        key_dimension=None,
    )


def classify_general_geometric_tolerance(
    text: str,
) -> _Classification | None:
    match = _GEOMETRIC_STANDARD.search(text)
    if match is None:
        return None
    tolerance_class = match.group("class").lower()
    return _Classification(
        category="applicability_rule",
        subtype="general_geometric_tolerance",
        parsed_parameters={
            "standard_code": "GB/T 1184",
            "tolerance_class": tolerance_class,
        },
        inspection_item="未注形位公差",
        inspection_standard=f"GB/T 1184-{tolerance_class}",
        key_dimension=None,
    )


def classify_default_chamfer(text: str) -> _Classification | None:
    match = _DEFAULT_CHAMFER.search(text)
    if match is None:
        return None
    size = match.group("size")
    return _Classification(
        category="applicability_rule",
        subtype="default_chamfer",
        parsed_parameters={"chamfer": f"C{size}"},
        inspection_item="未标注倒角",
        inspection_standard=None,
        key_dimension=f"C{size}",
    )


def classify_deburr(text: str) -> _Classification | None:
    if _DEBURR.search(text) is None:
        return None
    return _Classification(
        category="standalone_check",
        subtype="deburr",
        parsed_parameters={},
        inspection_item="锐边去毛刺",
        inspection_standard=text,
        key_dimension=None,
    )


def classify_surface_integrity(text: str) -> _Classification | None:
    if _SURFACE_INTEGRITY.search(text) is None:
        return None
    return _Classification(
        category="standalone_check",
        subtype="surface_integrity",
        parsed_parameters={},
        inspection_item="外观检查",
        inspection_standard=text,
        key_dimension=None,
    )


def classify_surface_treatment(text: str) -> _Classification | None:
    if _SURFACE_TREATMENT.search(text) is None:
        return None
    return _Classification(
        category="standalone_check",
        subtype="surface_treatment",
        parsed_parameters={},
        inspection_item="表面处理检查",
        inspection_standard=text,
        key_dimension=None,
    )


CLASSIFICATION_RULES = (
    ("general_dimensional_tolerance", classify_general_dimensional_tolerance),
    ("general_geometric_tolerance", classify_general_geometric_tolerance),
    ("default_chamfer", classify_default_chamfer),
    ("deburr", classify_deburr),
    ("surface_integrity", classify_surface_integrity),
    ("surface_treatment", classify_surface_treatment),
)


def classify_technical_requirement_entry(
    entry: TechnicalRequirementEntry,
) -> TechnicalRequirementDecision:
    classification: _Classification | None = None
    for _, classifier in CLASSIFICATION_RULES:
        classification = classifier(entry.normalized_text)
        if classification is not None:
            break

    if classification is None:
        unsupported_standard = bool(
            _UNKNOWN_DIMENSIONAL_STANDARD.search(entry.normalized_text)
            or _UNKNOWN_GEOMETRIC_STANDARD.search(entry.normalized_text)
        )
        classification = _Classification(
            category="unsupported" if unsupported_standard else "ambiguous",
            subtype="unsupported" if unsupported_standard else "ambiguous",
            parsed_parameters={},
            inspection_item=None,
            inspection_standard=None,
            key_dimension=None,
        )

    requirement_id = stable_candidate_id(
        "technical-requirement",
        *entry.source_segment_ids,
        entry.raw_text,
    )
    return TechnicalRequirementDecision(
        requirement_id=requirement_id,
        ordinal=entry.ordinal,
        raw_text=entry.raw_text,
        normalized_text=entry.normalized_text,
        source_location_ids=list(entry.source_location_ids),
        page_index=entry.page_index,
        coordinates=list(entry.coordinates),
        category=classification.category,
        subtype=classification.subtype,
        parsed_parameters=classification.parsed_parameters,
        match_outcome="unresolved",
        matched_candidate_ids=[],
        generated_candidate_id=None,
        rule_id=f"technical-requirement:{classification.subtype}",
        rule_version=TECHNICAL_REQUIREMENT_RULE_VERSION,
        review_required=True,
        sip_suggestion=SipSuggestion(
            inspection_item=classification.inspection_item,
            inspection_standard=classification.inspection_standard,
            key_dimension=classification.key_dimension,
            source_page=entry.page_index + 1,
            remarks=entry.raw_text,
        ),
    )
