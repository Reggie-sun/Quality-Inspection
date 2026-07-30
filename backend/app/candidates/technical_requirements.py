from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.candidates.confidence import ConfidenceDecisionContractError
from app.candidates.parser import normalize_text
from app.candidates.schemas import Candidate, stable_candidate_id
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
_EXPLICIT_CHAMFER = re.compile(
    r"(?:检查|检验|测量|确认|验证).*?倒角.*?(?:尺寸)?应为\s*"
    r"(?P<size>[0-9]+(?:\.[0-9]+)?\s*[×xX]\s*"
    r"[0-9]+(?:\.[0-9]+)?\s*°?)"
)
_DEBURR = re.compile(r"(?:锐边.*?(?:去除?|清除)毛刺|去除?毛刺)")
_SURFACE_INTEGRITY = re.compile(
    r"(?:表面|外观).*?(?:划痕|擦伤|损伤|裂纹)"
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
    heading_source_location_ids: tuple[str, ...] = ()


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


class TechnicalRequirementContractError(ConfidenceDecisionContractError):
    pass


@dataclass(frozen=True)
class TechnicalRequirementEvaluation:
    decisions: tuple[TechnicalRequirementDecision, ...]
    candidates: tuple[dict[str, Any], ...]


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
    return (
        -previous_height * 0.35
        <= vertical_gap
        <= max(4.0, previous_height * 0.75)
    )


def _same_requirement_column(
    heading: _ObservationSegment,
    current: _ObservationSegment,
) -> bool:
    if heading.observation.page_index != current.observation.page_index:
        return False
    if not _same_direction(
        heading.observation.direction,
        current.observation.direction,
    ):
        return False
    heading_width = max(heading.bbox_pdf[2] - heading.bbox_pdf[0], 1.0)
    heading_height = max(heading.bbox_pdf[3] - heading.bbox_pdf[1], 1.0)
    x_tolerance = max(8.0, heading_width * 0.75, heading_height * 2.0)
    return abs(current.bbox_pdf[0] - heading.bbox_pdf[0]) <= x_tolerance


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
    heading_source_location_ids: tuple[str, ...],
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
        heading_source_location_ids=heading_source_location_ids,
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
    heading_source_location_ids: tuple[str, ...] = ()
    heading_segment: _ObservationSegment | None = None

    def flush() -> None:
        nonlocal current_ordinal, current_segments, current_texts
        if current_ordinal is not None and current_segments:
            entries.append(
                _entry_from_segments(
                    current_ordinal,
                    current_segments,
                    current_texts,
                    heading_source_location_ids,
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
            heading_segment = segment
            heading_source_location_ids = (
                segment.observation.observation_id,
            )
            continue
        if not active_block:
            continue
        if heading_segment is None or not _same_requirement_column(
            heading_segment,
            segment,
        ):
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
            heading_segment = None
            heading_source_location_ids = ()
            continue
        if not _can_continue(current_segments[-1], segment):
            flush()
            active_block = False
            heading_segment = None
            heading_source_location_ids = ()
            continue
        current_segments.append(segment)
        current_texts.append(segment.text)

    flush()
    return tuple(entries)


def technical_requirement_source_location_ids(
    _observations: Sequence[TextObservation],
    entries: Sequence[TechnicalRequirementEntry],
) -> frozenset[str]:
    source_ids = {
        source_id
        for entry in entries
        for source_id in entry.source_location_ids
    }
    source_ids.update(
        source_id
        for entry in entries
        for source_id in entry.heading_source_location_ids
    )
    return frozenset(source_ids)


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
    if match is not None:
        size = f"C{match.group('size')}"
        category: RequirementCategory = "applicability_rule"
        inspection_item = "未标注倒角"
    else:
        match = _EXPLICIT_CHAMFER.search(text)
        if match is None:
            return None
        size = re.sub(r"\s*[xX×]\s*", "×", match.group("size"))
        category = "standalone_check"
        inspection_item = "倒角检查"
    return _Classification(
        category=category,
        subtype="default_chamfer",
        parsed_parameters={"chamfer": size},
        inspection_item=inspection_item,
        inspection_standard=None,
        key_dimension=size,
    )


def classify_deburr(text: str) -> _Classification | None:
    if _DEBURR.search(text) is None:
        return None
    return _Classification(
        category="standalone_check",
        subtype="deburr",
        parsed_parameters={},
        inspection_item="去毛刺与锐边检查",
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


_SUPPORTED_GENERAL_DIMENSION_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "radius",
    "angle",
}


def _candidate_identity(candidate: Mapping[str, Any]) -> str:
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise TechnicalRequirementContractError(
            "candidate identity must be one non-blank string"
        )
    return candidate_id


def _validated_matching_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if (
        not isinstance(candidates, Sequence)
        or isinstance(candidates, (str, bytes, bytearray))
        or isinstance(candidates, Mapping)
    ):
        raise TechnicalRequirementContractError(
            "matching candidates must be a non-string sequence"
        )
    frozen = tuple(candidates)
    candidate_ids = [_candidate_identity(candidate) for candidate in frozen]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise TechnicalRequirementContractError(
            "candidate identities must be unique for requirement matching"
        )
    return frozen


def evaluate_requirement(
    requirement: TechnicalRequirementEntry | TechnicalRequirementDecision,
    candidates: Sequence[Mapping[str, Any]],
) -> TechnicalRequirementDecision:
    decision = (
        classify_technical_requirement_entry(requirement)
        if isinstance(requirement, TechnicalRequirementEntry)
        else requirement.model_copy(deep=True)
    )
    validated_candidates = _validated_matching_candidates(candidates)

    if decision.category in {"unsupported", "ambiguous"}:
        return decision.model_copy(
            update={
                "match_outcome": "unresolved",
                "matched_candidate_ids": [],
                "generated_candidate_id": None,
                "review_required": True,
            }
        )

    matched_candidate_ids: list[str] = []
    if decision.subtype == "general_dimensional_tolerance":
        for candidate in validated_candidates:
            payload = candidate.get("payload")
            if not isinstance(payload, Mapping):
                raise TechnicalRequirementContractError(
                    f"candidate {_candidate_identity(candidate)} payload "
                    "must be one object"
                )
            if payload.get("item_type") not in _SUPPORTED_GENERAL_DIMENSION_TYPES:
                continue
            if (
                payload.get("upper_tolerance") is not None
                or payload.get("lower_tolerance") is not None
            ):
                continue
            matched_candidate_ids.append(_candidate_identity(candidate))

    if matched_candidate_ids:
        return decision.model_copy(
            update={
                "match_outcome": "matched_items",
                "matched_candidate_ids": sorted(matched_candidate_ids),
                "generated_candidate_id": None,
                "review_required": True,
            }
        )

    generated_candidate_id = stable_candidate_id(
        "technical-requirement-candidate",
        decision.requirement_id,
    )
    return decision.model_copy(
        update={
            "match_outcome": "global_scope",
            "matched_candidate_ids": [],
            "generated_candidate_id": generated_candidate_id,
            "review_required": True,
        }
    )


def _conflicting_requirement_ids(
    decisions: Sequence[TechnicalRequirementDecision],
) -> frozenset[str]:
    by_subtype: dict[str, list[TechnicalRequirementDecision]] = {}
    for decision in decisions:
        if decision.subtype not in {
            "general_dimensional_tolerance",
            "general_geometric_tolerance",
        }:
            continue
        by_subtype.setdefault(decision.subtype, []).append(decision)

    conflicting: set[str] = set()
    for group in by_subtype.values():
        parameter_sets = {
            tuple(sorted(decision.parsed_parameters.items()))
            for decision in group
        }
        if len(parameter_sets) > 1:
            conflicting.update(decision.requirement_id for decision in group)
    return frozenset(conflicting)


def _generated_requirement_candidate(
    decision: TechnicalRequirementDecision,
) -> dict[str, Any]:
    if decision.generated_candidate_id is None:
        raise TechnicalRequirementContractError(
            "global_scope requirement requires generated candidate identity"
        )
    candidate = Candidate(
        candidate_id=decision.generated_candidate_id,
        item_type="general_requirement",
        raw_text=decision.raw_text,
        normalized_text=decision.normalized_text,
        coordinates=decision.coordinates[0],
        scope="global_requirement",
        balloon_required=False,
        requires_confirmation=True,
    )
    return {
        "candidate_id": decision.generated_candidate_id,
        "payload": candidate.model_dump(mode="json", exclude_none=True),
        "source_location_ids": list(decision.source_location_ids),
        "source_truth_preserved": False,
        "technical_requirement_refs": [decision.requirement_id],
    }


def evaluate_technical_requirements(
    requirements: Sequence[
        TechnicalRequirementEntry | TechnicalRequirementDecision
    ],
    candidates: Sequence[Mapping[str, Any]],
) -> TechnicalRequirementEvaluation:
    validated_candidates = _validated_matching_candidates(candidates)
    candidate_copies = [
        copy.deepcopy(dict(candidate))
        for candidate in validated_candidates
    ]
    classified = [
        (
            classify_technical_requirement_entry(requirement)
            if isinstance(requirement, TechnicalRequirementEntry)
            else requirement.model_copy(deep=True)
        )
        for requirement in requirements
    ]
    conflicting_ids = _conflicting_requirement_ids(classified)
    decisions: list[TechnicalRequirementDecision] = []

    for requirement in classified:
        if requirement.requirement_id in conflicting_ids:
            decisions.append(
                requirement.model_copy(
                    update={
                        "match_outcome": "unresolved",
                        "matched_candidate_ids": [],
                        "generated_candidate_id": None,
                        "review_required": True,
                    }
                )
            )
            continue
        decision = evaluate_requirement(requirement, candidate_copies)
        decisions.append(decision)
        if decision.match_outcome == "matched_items":
            matched = set(decision.matched_candidate_ids)
            for candidate in candidate_copies:
                if _candidate_identity(candidate) not in matched:
                    continue
                refs = candidate.setdefault("technical_requirement_refs", [])
                if not isinstance(refs, list) or not all(
                    isinstance(ref, str) for ref in refs
                ):
                    raise TechnicalRequirementContractError(
                        "technical_requirement_refs must be a string list"
                    )
                refs.append(decision.requirement_id)
                candidate["technical_requirement_refs"] = sorted(set(refs))
        elif decision.match_outcome == "global_scope":
            candidate_copies.append(_generated_requirement_candidate(decision))

    return TechnicalRequirementEvaluation(
        decisions=tuple(decisions),
        candidates=tuple(candidate_copies),
    )


def reconcile_technical_requirements(
    requirements: Sequence[TechnicalRequirementDecision | Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> TechnicalRequirementEvaluation:
    """Reapply requirement ownership after another stage changes candidates."""
    decisions: list[TechnicalRequirementDecision] = []
    for index, requirement in enumerate(requirements):
        try:
            decisions.append(
                requirement.model_copy(deep=True)
                if isinstance(requirement, TechnicalRequirementDecision)
                else TechnicalRequirementDecision.model_validate(requirement)
            )
        except ValidationError as exc:
            raise TechnicalRequirementContractError(
                f"technical requirement at index {index} is invalid: {exc}"
            ) from exc

    requirement_ids = {decision.requirement_id for decision in decisions}
    if len(requirement_ids) != len(decisions):
        raise TechnicalRequirementContractError("duplicate requirement_id")
    generated_candidate_ids = {
        decision.generated_candidate_id
        for decision in decisions
        if decision.generated_candidate_id is not None
    }

    base_candidates: list[dict[str, Any]] = []
    for candidate in _validated_matching_candidates(candidates):
        if _candidate_identity(candidate) in generated_candidate_ids:
            continue
        candidate_copy = copy.deepcopy(dict(candidate))
        refs = candidate_copy.get("technical_requirement_refs")
        if refs is not None:
            if not isinstance(refs, list) or not all(
                isinstance(ref, str) for ref in refs
            ):
                raise TechnicalRequirementContractError(
                    "technical_requirement_refs must be a string list"
                )
            retained_refs = sorted(set(refs) - requirement_ids)
            if retained_refs:
                candidate_copy["technical_requirement_refs"] = retained_refs
            else:
                candidate_copy.pop("technical_requirement_refs", None)
        base_candidates.append(candidate_copy)

    return evaluate_technical_requirements(decisions, base_candidates)


def validate_technical_requirements(
    technical_requirements: Sequence[Mapping[str, Any]],
    *,
    candidate_ids: set[str],
) -> list[dict[str, Any]]:
    if (
        not isinstance(technical_requirements, Sequence)
        or isinstance(technical_requirements, (str, bytes, bytearray))
        or isinstance(technical_requirements, Mapping)
    ):
        raise TechnicalRequirementContractError(
            "technical_requirements must be a non-string sequence"
        )

    validated: list[TechnicalRequirementDecision] = []
    for index, requirement in enumerate(technical_requirements):
        if not isinstance(requirement, Mapping):
            raise TechnicalRequirementContractError(
                f"technical requirement at index {index} must be one object"
            )
        try:
            validated.append(
                TechnicalRequirementDecision.model_validate(requirement)
            )
        except ValidationError as exc:
            raise TechnicalRequirementContractError(
                f"technical requirement at index {index} is invalid: {exc}"
            ) from exc

    requirement_ids = [decision.requirement_id for decision in validated]
    if len(set(requirement_ids)) != len(requirement_ids):
        raise TechnicalRequirementContractError("duplicate requirement_id")

    for decision in validated:
        targets = decision.matched_candidate_ids
        if targets != sorted(set(targets)):
            raise TechnicalRequirementContractError(
                "matched_candidate_ids must use unique canonical order"
            )
        missing_targets = sorted(set(targets) - candidate_ids)
        if missing_targets:
            raise TechnicalRequirementContractError(
                "technical requirement references missing candidate: "
                + ", ".join(missing_targets)
            )
        if decision.match_outcome == "matched_items":
            if not targets or decision.generated_candidate_id is not None:
                raise TechnicalRequirementContractError(
                    "matched_items requires targets and forbids generated candidate"
                )
        elif decision.match_outcome == "global_scope":
            if (
                targets
                or decision.generated_candidate_id is None
                or decision.generated_candidate_id not in candidate_ids
            ):
                raise TechnicalRequirementContractError(
                    "global_scope requires one persisted generated candidate"
                )
        elif targets or decision.generated_candidate_id is not None:
            raise TechnicalRequirementContractError(
                "unresolved requirement cannot reference candidates"
            )

    return [
        decision.model_dump(mode="json")
        for decision in validated
    ]
