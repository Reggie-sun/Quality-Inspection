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

from app.candidates.duplicates import (
    DuplicateCandidate,
    DuplicateRelation,
    suggest_cross_view_duplicates,
)
from app.candidates.parser import normalize_text, parse_annotation
from app.candidates.schemas import stable_candidate_id
from app.candidates.symbol_review import (
    VISUAL_PROMPT_VERSION,
    VISUAL_SCHEMA_VERSION,
    ValidatedSymbolDetection,
    VisualReviewDecision,
    build_visual_cache_envelope,
    build_visual_failure_envelope,
    build_visual_request_evidence,
    canonical_visual_response_bytes,
    parse_visual_cache_envelope,
    parse_visual_request_evidence,
    parse_visual_symbol_json,
    plan_visual_batches,
    project_visual_page,
    validate_symbol_detections,
    visual_cache_identity,
    visual_cache_key,
    visual_review_prompt,
)
from app.capabilities.service import CapabilityUnavailable
from app.config import Settings
from app.pdf.coordinates import BBox
from app.pdf.schemas import TextObservation, VisualObservation
from app.pdf.visual_observations import reconstruct_visual_geometry_contexts
from app.processing.automatic_result import CandidateSnapshot, selected_observations
from app.providers.base import VisionResult
from app.providers.call_records import (
    ProviderCallRecord,
    persist_call_record,
    serialize_call_record,
)
from app.providers.qwen_vl import (
    VisualSymbolProviderError,
    canonicalize_visual_png,
    parse_candidate_json,
    validate_visual_request_metadata,
)
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
    candidate_id: str | None
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


def _render_visual_crop(page: pymupdf.Page, bbox: BBox) -> bytes:
    crop = pymupdf.Rect(bbox)
    rendered = crop * page.rotation_matrix
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(300 / 72, 300 / 72),
        clip=rendered,
        alpha=False,
    )
    if pixmap.width <= 0 or pixmap.height <= 0:
        raise CandidateAdvisorFailure("Visual symbol crop is unavailable")
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
    *,
    max_calls_by_page: dict[int, int] | None = None,
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
                candidate_id=str(candidate["candidate_id"]),
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
                candidate_id=None,
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
        page_cap = (
            MAX_CALLS_PER_PAGE
            if max_calls_by_page is None
            else max_calls_by_page.get(route.page_index, MAX_CALLS_PER_PAGE)
        )
        if calls_per_page[route.page_index] >= page_cap:
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


def _visual_retry_evidence_paths(
    project_id: str,
    cache_key: str,
) -> tuple[str, str, str]:
    filename = f"{cache_key}.attempt-1.json"
    return (
        f"projects/{project_id}/provider-calls/"
        f"qwen-symbol-retries/{filename}",
        f"projects/{project_id}/provider-requests/"
        f"qwen-symbol-retries/{filename}",
        f"projects/{project_id}/provider-responses/"
        f"qwen-symbol-retries/{filename}",
    )


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

    def _visual_cache_result(
        self,
        relative_path: str,
        *,
        audit_relative_path: str,
        crop_relative_path: str,
        request_relative_path: str,
        identity: dict[str, object],
    ) -> tuple[VisionResult, tuple[str, ...]] | None:
        cache_candidate = self._storage.root.joinpath(
            *relative_path.split("/")
        )
        current = self._storage.root
        cache_path_has_symlink = False
        for part in relative_path.split("/"):
            current /= part
            if current.is_symlink():
                cache_path_has_symlink = True
                break
        if not cache_candidate.exists() and not cache_path_has_symlink:
            return None
        try:
            cache_path = self._storage.resolve_resource_ref(
                f"asset://{relative_path}"
            )
            audit_path = self._storage.resolve_resource_ref(
                f"asset://{audit_relative_path}"
            )
            request_path = self._storage.resolve_resource_ref(
                f"asset://{request_relative_path}"
            )
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            audit_content = audit_path.read_bytes()
            audit = json.loads(audit_content)
            request_content = request_path.read_bytes()
            request_payload = json.loads(request_content)
            if (
                not isinstance(payload, dict)
                or not isinstance(audit, dict)
                or not isinstance(request_payload, dict)
            ):
                raise ValueError("cache values")
            request_id, response, usage = parse_visual_cache_envelope(
                payload,
                expected_identity=identity,
            )
            request_id, usage = validate_visual_request_metadata(
                request_id,
                usage,
            )
            request_evidence = parse_visual_request_evidence(
                request_payload,
                expected_crop_ref=f"asset://{crop_relative_path}",
                expected_crop_sha256=str(identity["crop_sha256"]),
                expected_usage=usage,
            )
            if _json_bytes(request_evidence) != request_content:
                raise ValueError("request evidence")
            crop_path = self._storage.resolve_resource_ref(
                request_evidence["crop_ref"]
            )
            response_content = canonical_visual_response_bytes(response)
            response_sha256 = hashlib.sha256(response_content).hexdigest()
            response_relative_path = (
                f"projects/{self._project_id}/provider-responses/"
                f"qwen-symbol/{response_sha256}.json"
            )
            response_path = self._storage.resolve_resource_ref(
                f"asset://{response_relative_path}"
            )
            if serialize_call_record(audit) != audit_content:
                raise ValueError("cache audit")
            retry_count = audit.get("retry_count")
            if (
                not isinstance(retry_count, int)
                or isinstance(retry_count, bool)
                or retry_count not in (0, 1)
            ):
                raise ValueError("cache retry count")
            expected_audit = {
                "provider": "qwen-vl",
                "request_id": request_id,
                "model": identity["model"],
                "prompt_version": VISUAL_PROMPT_VERSION,
                "schema_version": VISUAL_SCHEMA_VERSION,
                "input_image_count": 1,
                "estimated_cost": None,
                "logical_task_reused": False,
                "request_ref": f"asset://{request_relative_path}",
                "response_ref": f"asset://{response_relative_path}",
            }
            if any(
                audit.get(key) != value
                for key, value in expected_audit.items()
            ) or hashlib.sha256(crop_path.read_bytes()).hexdigest() != identity.get(
                "crop_sha256"
            ) or response_path.read_bytes() != response_content:
                raise ValueError("cache audit")

            cache_key = Path(audit_relative_path).stem
            retry_paths = _visual_retry_evidence_paths(
                self._project_id,
                cache_key,
            )
            retry_request_ids: tuple[str, ...] = ()
            retry_candidates = tuple(
                self._storage.root.joinpath(*path.split("/"))
                for path in retry_paths
            )
            if retry_count == 0:
                if any(
                    path.exists() or path.is_symlink()
                    for path in retry_candidates
                ):
                    raise ValueError("unexpected retry evidence")
            else:
                retry_audit_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[0]}"
                )
                retry_request_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[1]}"
                )
                retry_response_path = self._storage.resolve_resource_ref(
                    f"asset://{retry_paths[2]}"
                )
                retry_audit_content = retry_audit_path.read_bytes()
                retry_audit = json.loads(retry_audit_content)
                retry_request_content = retry_request_path.read_bytes()
                retry_request = json.loads(retry_request_content)
                retry_response_content = retry_response_path.read_bytes()
                retry_response = json.loads(retry_response_content)
                if (
                    not isinstance(retry_audit, dict)
                    or not isinstance(retry_request, dict)
                    or not isinstance(retry_response, dict)
                    or serialize_call_record(retry_audit)
                    != retry_audit_content
                    or retry_audit.get("request_id") == request_id
                ):
                    raise ValueError("retry evidence")
                expected_retry_audit = {
                    "provider": "qwen-vl",
                    "model": identity["model"],
                    "prompt_version": VISUAL_PROMPT_VERSION,
                    "schema_version": VISUAL_SCHEMA_VERSION,
                    "retry_count": 0,
                    "input_image_count": 1,
                    "estimated_cost": None,
                    "logical_task_reused": False,
                    "request_ref": f"asset://{retry_paths[1]}",
                    "response_ref": f"asset://{retry_paths[2]}",
                }
                if any(
                    retry_audit.get(key) != value
                    for key, value in expected_retry_audit.items()
                ):
                    raise ValueError("retry audit")
                retry_request_evidence = parse_visual_request_evidence(
                    retry_request,
                    expected_crop_ref=f"asset://{crop_relative_path}",
                    expected_crop_sha256=str(identity["crop_sha256"]),
                    expected_usage=retry_request.get("usage"),
                )
                expected_retry_response = build_visual_failure_envelope(
                    "tool_arguments_schema_invalid"
                )
                if (
                    _json_bytes(retry_request_evidence)
                    != retry_request_content
                    or retry_response != expected_retry_response
                    or _json_bytes(expected_retry_response)
                    != retry_response_content
                ):
                    raise ValueError("retry payload")
                retry_request_ids = (str(retry_audit["request_id"]),)
            return (
                VisionResult(
                    request_id=request_id,
                    payload=response,
                    usage=usage,
                ),
                (*retry_request_ids, request_id),
            )
        except Exception:
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor cache is invalid"
            ) from None

    def _visual_review_result(
        self,
        *,
        provider: object | None,
        crop_png: bytes,
        crop_bbox_pdf: BBox,
        source_sha256: str,
        visual_observations: Sequence[VisualObservation],
        text_observations: dict[str, TextObservation],
        model: str,
        allow_schema_retry: bool = False,
    ) -> tuple[VisionResult, object | None, tuple[str, ...]]:
        if not isinstance(allow_schema_retry, bool):
            raise ValueError("visual schema retry flag must be boolean")
        canonical_crop_png = canonicalize_visual_png(crop_png)
        crop_sha256 = hashlib.sha256(canonical_crop_png).hexdigest()
        visual_observation_ids = tuple(
            observation.observation_id
            for observation in visual_observations
        )
        identity = visual_cache_identity(
            source_sha256=source_sha256,
            visual_observation_ids=visual_observation_ids,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
            model=model,
        )
        cache_key = visual_cache_key(
            source_sha256=source_sha256,
            visual_observation_ids=visual_observation_ids,
            crop_bbox_pdf=crop_bbox_pdf,
            crop_sha256=crop_sha256,
            model=model,
        )
        cache_relative = (
            f"projects/{self._project_id}/provider-cache/qwen-symbol/"
            f"{cache_key}.json"
        )
        audit_relative = (
            f"projects/{self._project_id}/provider-calls/qwen-symbol/"
            f"{cache_key}.json"
        )
        crop_relative = (
            f"projects/{self._project_id}/provider-inputs/qwen-symbol/"
            f"{crop_sha256}.png"
        )
        request_relative = (
            f"projects/{self._project_id}/provider-requests/"
            f"qwen-symbol/{cache_key}.json"
        )
        cached = self._visual_cache_result(
            cache_relative,
            audit_relative_path=audit_relative,
            crop_relative_path=crop_relative,
            request_relative_path=request_relative,
            identity=identity,
        )
        if cached is not None:
            cached_result, cached_request_ids = cached
            if len(cached_request_ids) > 1 and not allow_schema_retry:
                raise CandidateAdvisorFailure(
                    "Visual symbol Advisor retry budget is invalid"
                )
            return cached_result, provider, cached_request_ids

        if provider is None:
            provider = self._provider_factory(self._settings)
        crop_write = self._storage.write_verified(
            crop_relative,
            canonical_crop_png,
            crop_sha256,
        )
        prompt = visual_review_prompt(
            visual_observations,
            text_observations=text_observations,
            crop_bbox_pdf=crop_bbox_pdf,
        )

        def call_once() -> tuple[
            VisionResult | None,
            tuple[str, dict[str, int], str] | None,
            int,
        ]:
            started = time.perf_counter_ns()
            result: VisionResult | None = None
            failure: tuple[str, dict[str, int], str] | None = None
            unexpected_failure = False
            try:
                raw_result = provider.review_symbols(
                    canonical_crop_png,
                    prompt,
                )
                response = parse_visual_symbol_json(raw_result.payload)
                request_id, usage = validate_visual_request_metadata(
                    raw_result.request_id,
                    raw_result.usage,
                )
                result = VisionResult(
                    request_id=request_id,
                    payload=response,
                    usage=usage,
                )
            except VisualSymbolProviderError as exc:
                failure = (
                    exc.request_id,
                    dict(exc.usage),
                    exc.failure_stage,
                )
            except CapabilityUnavailable:
                raise
            except Exception:
                unexpected_failure = True
            duration_ms = max(
                0,
                (time.perf_counter_ns() - started) // 1_000_000,
            )
            if unexpected_failure:
                raise CandidateAdvisorFailure(
                    "Visual symbol Advisor call failed"
                ) from None
            return result, failure, duration_ms

        def persist_failure(
            failure: tuple[str, dict[str, int], str],
            *,
            duration_ms: int,
            retry_count: int,
            audit_path: str,
            request_path: str,
            response_path: str,
        ) -> None:
            request_id, usage, failure_stage = failure
            request_content = _json_bytes(
                build_visual_request_evidence(
                    crop_ref=crop_write.resource_ref,
                    crop_sha256=crop_write.sha256,
                    usage=usage,
                )
            )
            request_write = self._storage.write_verified(
                request_path,
                request_content,
                hashlib.sha256(request_content).hexdigest(),
            )
            failure_content = _json_bytes(
                build_visual_failure_envelope(failure_stage)
            )
            failure_write = self._storage.write_verified(
                response_path,
                failure_content,
                hashlib.sha256(failure_content).hexdigest(),
            )
            persist_call_record(
                self._storage,
                audit_path,
                ProviderCallRecord(
                    provider="qwen-vl",
                    request_id=request_id,
                    model=model,
                    prompt_version=VISUAL_PROMPT_VERSION,
                    schema_version=VISUAL_SCHEMA_VERSION,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    input_image_count=1,
                    estimated_cost=None,
                    logical_task_reused=False,
                    request_ref=request_write.resource_ref,
                    response_ref=failure_write.resource_ref,
                ),
            )

        result, provider_failure, duration_ms = call_once()
        request_ids: list[str] = []
        retry_count = 0
        if (
            provider_failure is not None
            and allow_schema_retry
            and provider_failure[2] == "tool_arguments_schema_invalid"
        ):
            retry_paths = _visual_retry_evidence_paths(
                self._project_id,
                cache_key,
            )
            persist_failure(
                provider_failure,
                duration_ms=duration_ms,
                retry_count=0,
                audit_path=retry_paths[0],
                request_path=retry_paths[1],
                response_path=retry_paths[2],
            )
            request_ids.append(provider_failure[0])
            result, provider_failure, duration_ms = call_once()
            retry_count = 1

        if provider_failure is not None:
            persist_failure(
                provider_failure,
                duration_ms=duration_ms,
                retry_count=retry_count,
                audit_path=audit_relative,
                request_path=request_relative,
                response_path=(
                    f"projects/{self._project_id}/provider-responses/"
                    f"qwen-symbol/{cache_key}.json"
                ),
            )
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor response is invalid"
            ) from None
        if result is None:
            raise CandidateAdvisorFailure(
                "Visual symbol Advisor call failed"
            ) from None
        request_ids.append(result.request_id)
        request_content = _json_bytes(
            build_visual_request_evidence(
                crop_ref=crop_write.resource_ref,
                crop_sha256=crop_write.sha256,
                usage=result.usage,
            )
        )
        request_write = self._storage.write_verified(
            request_relative,
            request_content,
            hashlib.sha256(request_content).hexdigest(),
        )
        response_content = canonical_visual_response_bytes(result.payload)
        response_sha256 = hashlib.sha256(response_content).hexdigest()
        response_relative = (
            f"projects/{self._project_id}/provider-responses/"
            f"qwen-symbol/{response_sha256}.json"
        )
        response_write = self._storage.write_verified(
            response_relative,
            response_content,
            response_sha256,
        )
        cache_payload = build_visual_cache_envelope(
            request_id=result.request_id,
            identity=identity,
            response=result.payload,
            usage=result.usage,
        )
        cache_content = _json_bytes(cache_payload)
        self._storage.write_verified(
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
                prompt_version=VISUAL_PROMPT_VERSION,
                schema_version=VISUAL_SCHEMA_VERSION,
                duration_ms=duration_ms,
                retry_count=retry_count,
                input_image_count=1,
                estimated_cost=None,
                logical_task_reused=False,
                request_ref=request_write.resource_ref,
                response_ref=response_write.resource_ref,
            ),
        )
        return result, provider, tuple(request_ids)

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
        visual_batches = plan_visual_batches(pages, snapshot)
        planned_visual_calls_by_page = {
            page.page_index: len(visual_batches[index])
            for index, page in enumerate(pages)
        }
        routes = _route_objects(
            pages,
            snapshot,
            max_calls_by_page={
                page_index: MAX_CALLS_PER_PAGE - count
                for page_index, count in planned_visual_calls_by_page.items()
            },
        )
        model = self._settings.qwen_model.strip()
        provider: object | None = None
        candidates = [dict(candidate) for candidate in snapshot.candidates]
        coverage_entries = list(snapshot.coverage_entries)
        provider_call_ids = list(snapshot.provider_call_ids)
        observations = {
            observation.observation_id: observation
            for observation in selected_observations(pages)
        }
        all_text_observations = tuple(
            observation
            for page in pages
            for observation in page.observations
        )
        text_observations_by_id = {
            observation.observation_id: observation
            for observation in all_text_observations
        }
        visual_observations = {
            observation.observation_id: observation
            for page in pages
            for observation in page.visual_observations
        }
        visual_coverage_indexes = {
            entry.observation_id: index
            for index, entry in enumerate(coverage_entries)
            if entry.observation_id in visual_observations
        }
        contexts = {
            item.observation_id: item
            for item in (
                reconstruct_visual_geometry_contexts(pdf_path, pages)
                if any(visual_batches)
                else ()
            )
        }
        source_sha256 = (
            hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
            if any(visual_batches)
            else ""
        )
        candidates_changed = False
        visual_retry_available = True
        actual_visual_calls_by_page = {
            page.page_index: 0
            for page in pages
        }
        document = pymupdf.open(pdf_path)
        try:
            accepted_by_page: list[list[ValidatedSymbolDetection]] = [
                [] for _ in pages
            ]
            rejection_sets_by_page: list[dict[str, set[str]]] = [
                {} for _ in pages
            ]
            for page_position, page_batches in enumerate(visual_batches):
                page_inventory = pages[page_position]
                page = document[page_inventory.page_index]
                for batch in page_batches:
                    batch_observations = tuple(
                        visual_observations[identity]
                        for identity in batch.observation_ids
                    )
                    crop_png = _render_visual_crop(
                        page,
                        batch.crop_bbox_pdf,
                    )
                    result, provider, request_ids = self._visual_review_result(
                        provider=provider,
                        crop_png=crop_png,
                        crop_bbox_pdf=batch.crop_bbox_pdf,
                        source_sha256=source_sha256,
                        visual_observations=batch_observations,
                        text_observations=text_observations_by_id,
                        model=model,
                        allow_schema_retry=(
                            visual_retry_available
                            and len(page_batches) < MAX_CALLS_PER_PAGE
                        ),
                    )
                    actual_visual_calls_by_page[
                        page_inventory.page_index
                    ] += len(request_ids)
                    if len(request_ids) > 1:
                        visual_retry_available = False
                    accepted, rejected = validate_symbol_detections(
                        result.payload,
                        visual_observation_ids=batch.observation_ids,
                        text_allowlists={
                            item.observation_id:
                            item.associated_text_observation_ids
                            for item in batch_observations
                        },
                        crop_bbox_pdf=batch.crop_bbox_pdf,
                    )
                    accepted_by_page[page_position].extend(accepted)
                    rejection_sets = rejection_sets_by_page[page_position]
                    for rejected_item in rejected:
                        affected = (
                            (rejected_item.visual_observation_id,)
                            if rejected_item.visual_observation_id
                            in batch.observation_ids
                            else batch.observation_ids
                        )
                        for identity in affected:
                            rejection_sets.setdefault(identity, set()).add(
                                rejected_item.rejection_code
                            )
                    provider_call_ids.extend(request_ids)

            base_candidates = tuple(candidates)
            visual_decisions = []
            for page_position, page in enumerate(pages):
                visual_decisions.extend(
                    project_visual_page(
                        visual_observations=page.visual_observations,
                        detections=tuple(
                            accepted_by_page[page_position]
                        ),
                        rejection_codes={
                            identity: sorted(codes)[0]
                            for identity, codes in (
                                rejection_sets_by_page[
                                    page_position
                                ].items()
                            )
                        },
                        text_observations=all_text_observations,
                        candidates=base_candidates,
                        geometry_contexts=contexts,
                    )
                )

            retirement_by_candidate: dict[str, VisualReviewDecision] = {}
            replacement_by_candidate: dict[str, dict[str, Any]] = {}
            appended_by_candidate: dict[str, dict[str, Any]] = {}
            for decision in visual_decisions:
                review: dict[str, object] = {
                    "route": "visual_symbol",
                    "schema_version": VISUAL_SCHEMA_VERSION,
                    "symbol_kinds": list(decision.symbol_kinds),
                    "rejection_code": decision.rejection_code,
                }
                if (
                    decision.disposition == "candidate"
                    and decision.candidate_envelope is not None
                    and decision.candidate_id is not None
                ):
                    target = (
                        replacement_by_candidate
                        if decision.existing_candidate_index is not None
                        else appended_by_candidate
                    )
                    target[decision.candidate_id] = (
                        decision.candidate_envelope
                    )
                elif (
                    decision.rejection_code is None
                    and decision.disposition
                    in {"reference_context", "non_inspection"}
                    and decision.existing_candidate_index is not None
                ):
                    retired = base_candidates[
                        decision.existing_candidate_index
                    ]
                    retirement_by_candidate[
                        str(retired["candidate_id"])
                    ] = decision

                coverage_index = visual_coverage_indexes[
                    decision.observation_id
                ]
                coverage_entries[coverage_index] = replace(
                    coverage_entries[coverage_index],
                    disposition=decision.disposition,
                    source_location_id=decision.observation_id,
                    coordinates=decision.coordinates,
                    candidate_id=decision.candidate_id,
                    requires_confirmation=(
                        coverage_entries[
                            coverage_index
                        ].requires_confirmation
                        or decision.requires_confirmation
                    )
                    if decision.disposition != "reference_context"
                    else decision.requires_confirmation,
                    advisor_review=review,
                )

            if replacement_by_candidate:
                candidates = [
                    replacement_by_candidate.get(
                        str(candidate["candidate_id"]),
                        candidate,
                    )
                    for candidate in candidates
                ]
            for candidate_id, envelope in appended_by_candidate.items():
                if not any(
                    str(candidate["candidate_id"]) == candidate_id
                    for candidate in candidates
                ):
                    candidates.append(envelope)
            if retirement_by_candidate:
                candidates = [
                    candidate
                    for candidate in candidates
                    if str(candidate["candidate_id"])
                    not in retirement_by_candidate
                ]
                for index, entry in enumerate(coverage_entries):
                    if (
                        entry.candidate_id is None
                        or entry.candidate_id
                        not in retirement_by_candidate
                    ):
                        continue
                    retirement = retirement_by_candidate[
                        entry.candidate_id
                    ]
                    coverage_entries[index] = replace(
                        entry,
                        disposition=retirement.disposition,
                        candidate_id=None,
                        requires_confirmation=(
                            retirement.requires_confirmation
                        ),
                        advisor_review={
                            "route": "visual_symbol",
                            "schema_version": VISUAL_SCHEMA_VERSION,
                            "symbol_kinds": list(
                                retirement.symbol_kinds
                            ),
                            "rejection_code": None,
                        },
                    )
            candidates_changed = candidates != list(base_candidates)

            if not routes and not any(visual_batches):
                return snapshot

            text_calls_by_page = {
                page.page_index: 0
                for page in pages
            }
            for frozen_route in routes:
                if (
                    actual_visual_calls_by_page[frozen_route.page_index]
                    + text_calls_by_page[frozen_route.page_index]
                    >= MAX_CALLS_PER_PAGE
                ):
                    continue
                if frozen_route.candidate_id is not None:
                    current_indexes = [
                        index
                        for index, candidate in enumerate(candidates)
                        if str(candidate.get("candidate_id"))
                        == frozen_route.candidate_id
                    ]
                else:
                    current_indexes = [
                        index
                        for index, candidate in enumerate(candidates)
                        if set(frozen_route.source_ids).intersection(
                            candidate.get("source_location_ids", ())
                        )
                    ]
                if len(current_indexes) > 1:
                    continue
                if (
                    frozen_route.candidate_id is not None
                    and not current_indexes
                ):
                    continue
                route = replace(
                    frozen_route,
                    candidate_index=(
                        current_indexes[0] if current_indexes else None
                    ),
                )
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
                text_calls_by_page[route.page_index] += 1
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
                        if updated_payload != candidate.get("payload"):
                            candidates_changed = True
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
                    candidates_changed = True
                else:
                    coverage_entries[route.coverage_index] = replace(
                        coverage_entries[route.coverage_index],
                        advisor_review=advisor_review,
                    )
        finally:
            document.close()

        duplicate_relations = (
            _duplicate_relations(candidates, observations)
            if candidates_changed
            else snapshot.duplicate_relations
        )
        return CandidateSnapshot(
            candidates=tuple(candidates),
            coverage_entries=tuple(coverage_entries),
            expected_observation_ids=snapshot.expected_observation_ids,
            duplicate_relations=duplicate_relations,
            provider_call_ids=tuple(provider_call_ids),
            required_visual_observation_ids=(
                snapshot.required_visual_observation_ids
            ),
        )
