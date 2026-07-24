from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pymupdf

from app.candidates.coverage import CoverageEntry
from app.candidates.duplicates import (
    DuplicateCandidate,
    DuplicateRelation,
    suggest_cross_view_duplicates,
)
from app.candidates.parser import normalize_text, parse_annotation
from app.candidates.schemas import stable_candidate_id
from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.pdf.coordinates import BBox
from app.pdf.schemas import TextObservation
from app.processing.automatic_result import CandidateSnapshot, selected_observations
from app.providers.base import VisionResult
from app.providers.call_records import ProviderCallRecord, persist_call_record
from app.providers.qwen_vl import parse_candidate_json
from app.providers.runtime import VisionProviderFactory
from app.storage.local import LocalFileStorage


PROMPT_VERSION = "candidate-review-prompt/2"
SCHEMA_VERSION = "candidate-review/1"
ADAPTER_VERSION = "qwen-openai-compatible/1"
MAX_CALLS_PER_PAGE = 16
RENDER_SCALE = 2.0
ALLOWED_SUGGESTION_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
    "general_requirement",
    "composite",
    "geometric_tolerance",
    "roughness",
    "weld",
}
_PARSEABLE_TYPES = {
    "linear_dimension",
    "diameter_dimension",
    "thread",
    "radius",
    "angle",
}
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9-]+$")
_CACHE_FIELDS = {
    "cache_schema_version",
    "provider",
    "request_id",
    "model",
    "prompt_version",
    "schema_version",
    "crop_sha256",
    "suggestion",
    "usage",
}


class CandidateAdvisorFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutedObject:
    page_index: int
    source_ids: tuple[str, ...]
    raw_text: str
    expected_type: str | None
    review_reason: str
    bbox_pdf: BBox
    candidate_index: int | None
    coverage_index: int
    requires_confirmation: bool


def _bbox_union(observations: Sequence[TextObservation]) -> BBox:
    return (
        min(observation.bbox_pdf[0] for observation in observations),
        min(observation.bbox_pdf[1] for observation in observations),
        max(observation.bbox_pdf[2] for observation in observations),
        max(observation.bbox_pdf[3] for observation in observations),
    )


def _review_prompt(route: RoutedObject) -> str:
    item_type_schema: dict[str, object] = (
        {"const": route.expected_type}
        if route.expected_type is not None
        else {"enum": sorted(ALLOWED_SUGGESTION_TYPES)}
    )
    confirmation_schema: dict[str, object] = (
        {"const": True}
        if route.requires_confirmation
        else {"type": "boolean"}
    )
    return json.dumps(
        {
            "task": "review_local_engineering_annotation",
            "raw_text": route.raw_text,
            "expected_type": route.expected_type,
            "review_reason": route.review_reason,
            "output_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version",
                    "raw_text",
                    "item_type",
                    "normalized_text",
                    "requires_confirmation",
                ],
                "properties": {
                    "schema_version": {"const": SCHEMA_VERSION},
                    "raw_text": {"const": route.raw_text},
                    "item_type": item_type_schema,
                    "normalized_text": {
                        "type": "string",
                        "minLength": 1,
                    },
                    "requires_confirmation": confirmation_schema,
                },
            },
            "constraints": [
                "do_not_translate_raw_text",
                "do_not_guess_missing_context",
                "keep_or_raise_requires_confirmation",
                "return_frozen_schema_only",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _crop_rect(page: pymupdf.Page, bbox: BBox) -> tuple[pymupdf.Rect, float]:
    source = pymupdf.Rect(bbox)
    padding = min(24.0, max(6.0, source.height))
    crop = pymupdf.Rect(
        source.x0 - padding,
        source.y0 - padding,
        source.x1 + padding,
        source.y1 + padding,
    ) & page.rect
    if crop.is_empty or crop.get_area() <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return crop, padding


def _render_crop(page: pymupdf.Page, crop: pymupdf.Rect) -> bytes:
    rendered = crop * page.rotation_matrix
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE),
        clip=rendered,
        alpha=False,
    )
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise CandidateAdvisorFailure("Vision candidate crop is unavailable")
    return pixmap.tobytes("png")


def _candidate_reason(
    payload: dict[str, Any],
    observations: Sequence[TextObservation],
) -> tuple[str, str | None] | None:
    coarse_type = payload.get("coarse_type")
    if coarse_type in {"geometric_tolerance", "roughness", "weld"}:
        return "coarse_type", str(coarse_type)
    item_type = payload.get("item_type")
    if item_type == "composite":
        return "composite", "composite"
    if payload.get("requires_confirmation") is True:
        return "confirmation", str(item_type) if item_type is not None else None
    if any(observation.source_type == "ocr" for observation in observations):
        expected = coarse_type if coarse_type is not None else item_type
        return "ocr_source", str(expected) if expected is not None else None
    return None


def _route_objects(
    pages: Sequence[Any],
    snapshot: CandidateSnapshot,
) -> tuple[RoutedObject, ...]:
    observations = {
        observation.observation_id: observation
        for observation in selected_observations(pages)
    }
    coverage_indexes = {
        entry.observation_id: index
        for index, entry in enumerate(snapshot.coverage_entries)
    }
    routes: list[RoutedObject] = []

    for candidate_index, candidate in enumerate(snapshot.candidates):
        payload = candidate.get("payload")
        source_ids = tuple(
            str(source_id)
            for source_id in candidate.get("source_location_ids", ())
            if str(source_id) in observations
        )
        members = tuple(observations[source_id] for source_id in source_ids)
        if not isinstance(payload, dict) or not members:
            continue
        reason = _candidate_reason(payload, members)
        if reason is None:
            continue
        review_reason, expected_type = reason
        routes.append(
            RoutedObject(
                page_index=members[0].page_index,
                source_ids=source_ids,
                raw_text=str(payload.get("raw_text", members[0].raw_text)),
                expected_type=expected_type,
                review_reason=review_reason,
                bbox_pdf=_bbox_union(members),
                candidate_index=candidate_index,
                coverage_index=coverage_indexes[source_ids[0]],
                requires_confirmation=bool(
                    payload.get("requires_confirmation", False)
                ),
            )
        )

    candidate_source_ids = {
        source_id
        for candidate in snapshot.candidates
        for source_id in candidate.get("source_location_ids", ())
    }
    for coverage_index, entry in enumerate(snapshot.coverage_entries):
        if (
            entry.disposition != "ambiguous"
            or entry.observation_id in candidate_source_ids
        ):
            continue
        observation = observations.get(entry.observation_id)
        if observation is None:
            continue
        routes.append(
            RoutedObject(
                page_index=observation.page_index,
                source_ids=(observation.observation_id,),
                raw_text=observation.raw_text,
                expected_type=None,
                review_reason="parser_failed",
                bbox_pdf=observation.bbox_pdf,
                candidate_index=None,
                coverage_index=coverage_index,
                requires_confirmation=True,
            )
        )

    routes.sort(
        key=lambda route: (
            route.page_index,
            route.bbox_pdf[1],
            route.bbox_pdf[0],
            route.source_ids,
        )
    )
    calls_per_page: dict[int, int] = defaultdict(int)
    bounded: list[RoutedObject] = []
    for route in routes:
        if calls_per_page[route.page_index] >= MAX_CALLS_PER_PAGE:
            continue
        calls_per_page[route.page_index] += 1
        bounded.append(route)
    return tuple(bounded)


def _rejection_code(
    route: RoutedObject,
    payload: dict[str, Any],
) -> str | None:
    if normalize_text(str(payload.get("raw_text", ""))) != normalize_text(
        route.raw_text
    ):
        return "raw_text_mismatch"
    if payload.get("item_type") not in ALLOWED_SUGGESTION_TYPES:
        return "unknown_type"
    if (
        route.expected_type is not None
        and payload.get("item_type") != route.expected_type
    ):
        return "type_mismatch"
    if (
        route.requires_confirmation
        and payload.get("requires_confirmation") is False
    ):
        return "confirmation_downgrade"
    return None


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _cache_key(
    *,
    model: str,
    route: RoutedObject,
    crop_bbox_pdf: tuple[float, float, float, float],
    crop_sha256: str,
) -> str:
    document = {
        "provider_role": "advisor",
        "adapter_version": ADAPTER_VERSION,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "page_index": route.page_index,
        "crop_bbox_pdf": list(crop_bbox_pdf),
        "crop_sha256": crop_sha256,
    }
    return hashlib.sha256(_json_bytes(document)).hexdigest()


def _validated_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
    return parse_candidate_json(_json_bytes(payload).decode("utf-8"))


def _duplicate_relations(
    candidates: Sequence[dict[str, Any]],
    observations: dict[str, TextObservation],
) -> tuple[DuplicateRelation, ...]:
    duplicate_inputs: list[DuplicateCandidate] = []
    for candidate in candidates:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            continue
        source_ids = [
            str(source_id)
            for source_id in candidate.get("source_location_ids", ())
        ]
        source = next(
            (
                observations[source_id]
                for source_id in source_ids
                if source_id in observations
            ),
            None,
        )
        if source is None:
            continue
        duplicate_inputs.append(
            DuplicateCandidate(
                candidate_id=str(candidate["candidate_id"]),
                normalized_text=str(
                    payload.get("normalized_text", payload.get("raw_text", ""))
                ),
                view_id=f"page:{source.page_index}",
                disposition="candidate",
            )
        )
    return tuple(suggest_cross_view_duplicates(duplicate_inputs))


class CandidateAdvisor:
    def __init__(
        self,
        settings: Settings,
        storage: LocalFileStorage,
        *,
        project_id: str,
        provider_factory: VisionProviderFactory,
    ) -> None:
        if _SAFE_PROJECT_ID.fullmatch(project_id) is None:
            raise ValueError("project_id must be one safe path segment")
        self._settings = settings
        self._storage = storage
        self._project_id = project_id
        self._provider_factory = provider_factory

    def _cache_result(
        self,
        relative_path: str,
        *,
        audit_relative_path: str,
        crop_sha256: str,
        model: str,
    ) -> VisionResult | None:
        cache_path = self._storage.root.joinpath(*relative_path.split("/"))
        if not cache_path.exists():
            return None
        try:
            self._storage.resolve_resource_ref(f"asset://{audit_relative_path}")
        except ValueError:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor cache audit record is missing"
            ) from None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != _CACHE_FIELDS:
                raise ValueError("cache fields")
            if (
                payload["cache_schema_version"] != "candidate-advisor-cache/1"
                or payload["provider"] != "qwen-vl"
                or payload["model"] != model
                or payload["prompt_version"] != PROMPT_VERSION
                or payload["schema_version"] != SCHEMA_VERSION
                or payload["crop_sha256"] != crop_sha256
                or not isinstance(payload["request_id"], str)
                or not payload["request_id"].strip()
                or not isinstance(payload["suggestion"], dict)
                or not isinstance(payload["usage"], dict)
            ):
                raise ValueError("cache values")
            suggestion = _validated_suggestion(payload["suggestion"])
            usage = {
                str(key): value
                for key, value in payload["usage"].items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            if len(usage) != len(payload["usage"]):
                raise ValueError("cache usage")
            return VisionResult(
                request_id=payload["request_id"],
                payload=suggestion,
                usage=usage,
            )
        except Exception:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor cache is invalid"
            ) from None

    def _review_result(
        self,
        *,
        provider: object | None,
        route: RoutedObject,
        crop_png: bytes,
        crop_bbox_pdf: tuple[float, float, float, float],
        padding_pdf: float,
        model: str,
    ) -> tuple[VisionResult, object | None]:
        del padding_pdf
        crop_sha256 = hashlib.sha256(crop_png).hexdigest()
        cache_key = _cache_key(
            model=model,
            route=route,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
        )
        cache_relative = (
            f"projects/{self._project_id}/provider-cache/qwen/{cache_key}.json"
        )
        audit_relative = (
            f"projects/{self._project_id}/provider-calls/qwen/{cache_key}.json"
        )
        cached = self._cache_result(
            cache_relative,
            audit_relative_path=audit_relative,
            crop_sha256=crop_sha256,
            model=model,
        )
        if cached is not None:
            return cached, provider

        if provider is None:
            provider = self._provider_factory(self._settings)
        started = time.perf_counter_ns()
        try:
            raw_result = provider.review_candidate(
                crop_png,
                _review_prompt(route),
            )
            suggestion = _validated_suggestion(raw_result.payload)
            if (
                not isinstance(raw_result.request_id, str)
                or not raw_result.request_id.strip()
            ):
                raise ValueError("missing request ID")
            result = VisionResult(
                request_id=raw_result.request_id,
                payload=suggestion,
                usage=dict(raw_result.usage),
            )
        except CapabilityUnavailable:
            raise
        except Exception:
            raise CandidateAdvisorFailure(
                "Vision candidate Advisor call failed"
            ) from None
        duration_ms = max(0, (time.perf_counter_ns() - started) // 1_000_000)

        crop_relative = (
            f"projects/{self._project_id}/provider-inputs/qwen/"
            f"{crop_sha256}.png"
        )
        crop_write = self._storage.write_verified(
            crop_relative,
            crop_png,
            crop_sha256,
        )
        cache_payload = {
            "cache_schema_version": "candidate-advisor-cache/1",
            "provider": "qwen-vl",
            "request_id": result.request_id,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "crop_sha256": crop_sha256,
            "suggestion": result.payload,
            "usage": result.usage,
        }
        cache_content = _json_bytes(cache_payload)
        cache_write = self._storage.write_verified(
            cache_relative,
            cache_content,
            hashlib.sha256(cache_content).hexdigest(),
        )
        persist_call_record(
            self._storage,
            audit_relative,
            ProviderCallRecord(
                provider="qwen-vl",
                request_id=result.request_id,
                model=model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                duration_ms=duration_ms,
                retry_count=0,
                input_image_count=1,
                estimated_cost=None,
                logical_task_reused=False,
                request_ref=crop_write.resource_ref,
                response_ref=cache_write.resource_ref,
            ),
        )
        return result, provider

    def review(
        self,
        pdf_path: Path,
        pages: Sequence[Any],
        snapshot: CandidateSnapshot,
    ) -> CandidateSnapshot:
        routes = _route_objects(pages, snapshot)
        if not routes:
            return snapshot

        model = self._settings.qwen_model.strip()
        provider: object | None = None
        candidates = [dict(candidate) for candidate in snapshot.candidates]
        coverage_entries = list(snapshot.coverage_entries)
        provider_call_ids = list(snapshot.provider_call_ids)
        observations = {
            observation.observation_id: observation
            for observation in selected_observations(pages)
        }
        promoted = False
        document = pymupdf.open(pdf_path)
        try:
            for route in routes:
                page = document[route.page_index]
                crop, padding = _crop_rect(page, route.bbox_pdf)
                crop_png = _render_crop(page, crop)
                crop_bbox_pdf = (
                    float(crop.x0),
                    float(crop.y0),
                    float(crop.x1),
                    float(crop.y1),
                )
                result, provider = self._review_result(
                    provider=provider,
                    route=route,
                    crop_png=crop_png,
                    crop_bbox_pdf=crop_bbox_pdf,
                    padding_pdf=padding,
                    model=model,
                )
                rejection_code = _rejection_code(route, result.payload)

                updated_payload: dict[str, Any] | None = None
                promoted_candidate: dict[str, Any] | None = None
                if rejection_code is None and route.candidate_index is None:
                    try:
                        parsed = parse_annotation(
                            str(result.payload["normalized_text"])
                        )
                    except ValueError:
                        rejection_code = "local_parse_failed"
                    else:
                        if parsed.item_type != result.payload["item_type"]:
                            rejection_code = "type_mismatch"
                        else:
                            parsed = parsed.model_copy(
                                update={
                                    "candidate_id": stable_candidate_id(
                                        "annotation",
                                        route.raw_text,
                                    ),
                                    "raw_text": route.raw_text,
                                    "coordinates": route.bbox_pdf,
                                    "requires_confirmation": True,
                                }
                            )
                            promoted_candidate = {
                                "candidate_id": parsed.candidate_id,
                                "payload": parsed.model_dump(
                                    mode="json",
                                    exclude_none=True,
                                ),
                                "source_location_ids": list(route.source_ids),
                            }
                elif rejection_code is None and route.candidate_index is not None:
                    current_payload = candidates[route.candidate_index].get(
                        "payload"
                    )
                    if isinstance(current_payload, dict):
                        updated_payload = dict(current_payload)
                        item_type = current_payload.get("item_type")
                        if item_type in _PARSEABLE_TYPES:
                            try:
                                parsed = parse_annotation(
                                    str(result.payload["normalized_text"])
                                )
                            except ValueError:
                                rejection_code = "local_parse_failed"
                            else:
                                if parsed.item_type != item_type:
                                    rejection_code = "type_mismatch"
                                else:
                                    updated_payload["normalized_text"] = (
                                        parsed.normalized_text
                                    )
                        if rejection_code is None:
                            updated_payload["requires_confirmation"] = bool(
                                current_payload.get(
                                    "requires_confirmation",
                                    False,
                                )
                                or result.payload["requires_confirmation"]
                            )

                advisor_review: dict[str, object] = {
                    "provider_role": "advisor",
                    "review_reason": route.review_reason,
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "schema_version": SCHEMA_VERSION,
                    "page_index": route.page_index,
                    "crop_bbox_pdf": list(crop_bbox_pdf),
                    "padding_pdf": float(padding),
                    "crop_sha256": hashlib.sha256(crop_png).hexdigest(),
                    "validated": rejection_code is None,
                    "rejection_code": rejection_code,
                }
                provider_call_ids.append(result.request_id)
                if route.candidate_index is not None:
                    candidate = dict(candidates[route.candidate_index])
                    if rejection_code is None and updated_payload is not None:
                        candidate["payload"] = updated_payload
                    candidate["advisor_review"] = advisor_review
                    candidates[route.candidate_index] = candidate
                elif rejection_code is None and promoted_candidate is not None:
                    promoted_candidate["advisor_review"] = advisor_review
                    candidates.append(promoted_candidate)
                    coverage_entries[route.coverage_index] = replace(
                        coverage_entries[route.coverage_index],
                        disposition="candidate",
                        candidate_id=str(promoted_candidate["candidate_id"]),
                        requires_confirmation=True,
                        advisor_review=advisor_review,
                    )
                    promoted = True
                else:
                    coverage_entries[route.coverage_index] = replace(
                        coverage_entries[route.coverage_index],
                        advisor_review=advisor_review,
                    )
        finally:
            document.close()

        duplicate_relations = (
            _duplicate_relations(candidates, observations)
            if promoted
            else snapshot.duplicate_relations
        )
        return CandidateSnapshot(
            candidates=tuple(candidates),
            coverage_entries=tuple(coverage_entries),
            expected_observation_ids=snapshot.expected_observation_ids,
            duplicate_relations=duplicate_relations,
            provider_call_ids=tuple(provider_call_ids),
        )
