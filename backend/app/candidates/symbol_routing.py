from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.candidates.local_symbol_resolution import (
    LOCAL_SYMBOL_FAMILIES,
    LocalResolution,
)
from app.candidates.symbol_review import VisualReviewDecision


RoutingDisposition = Literal["locally_resolved", "escalate", "block"]
SymbolRecognitionMode = Literal[
    "legacy_high_recall",
    "shadow_uncertainty",
    "production_uncertainty",
]

SYMBOL_ROUTING_SCHEMA_VERSION = "symbol-routing-decision/1"
SYMBOL_ROUTER_VERSION = "symbol-uncertainty-router/1"
SYMBOL_RECOGNITION_MODES = frozenset(
    {
        "legacy_high_recall",
        "shadow_uncertainty",
        "production_uncertainty",
    }
)
_MODE_ROUTER_VERSION = {
    "legacy_high_recall": "legacy",
    "shadow_uncertainty": SYMBOL_ROUTER_VERSION,
    "production_uncertainty": SYMBOL_ROUTER_VERSION,
}
LOCAL_RESOLUTION_REASON_CODES = frozenset(
    {
        "native_symbol_explicit",
        "deterministic_geometry_complete",
        "local_projection_complete",
    }
)
ESCALATION_REASON_CODES = frozenset(
    {
        "local_evidence_conflict",
        "local_parse_incomplete",
        "unknown_symbol_pattern",
        "ambiguous_component_grouping",
        "missing_local_discriminator",
        "local_validator_disagreement",
    }
)
BLOCK_REASON_CODES = frozenset(
    {
        "source_reconstruction_mismatch",
        "visual_geometry_invalid",
        "routing_contract_invalid",
        "coverage_lineage_incomplete",
    }
)
_ALLOWED_PROJECTION_SEMANTICS = {
    "diameter": (
        "candidate",
        frozenset({("diameter",), ("depth", "diameter")}),
    ),
    "depth": ("candidate", frozenset({("depth",)})),
    "surface_roughness": (
        "candidate",
        frozenset({("surface_roughness",)}),
    ),
    "datum_reference": (
        "reference_context",
        frozenset({("datum_reference",)}),
    ),
    "revision_marker": (
        "non_inspection",
        frozenset({("revision_marker",)}),
    ),
}


@dataclass(frozen=True)
class RoutingDecision:
    schema_version: str
    router_version: str
    visual_observation_id: str
    input_sha256: str
    disposition: RoutingDisposition
    local_resolution_reason_codes: tuple[str, ...]
    escalation_reason_codes: tuple[str, ...]
    block_reason_codes: tuple[str, ...]
    requires_confirmation: bool


def _is_lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_reason_array(
    value: object,
    allowed_reasons: frozenset[str],
) -> bool:
    if (
        not isinstance(value, tuple)
        or not value
        or any(not isinstance(reason, str) for reason in value)
    ):
        return False
    return (
        value == tuple(sorted(set(value)))
        and set(value).issubset(allowed_reasons)
    )


def _validate_routing_decision(decision: object) -> RoutingDecision:
    """Validate the structural versioned exact-one decision contract.

    Consumer-specific semantic evidence binding is validated by that
    consumer; the escalation planner binds this record to LocalResolution.
    """
    if not isinstance(decision, RoutingDecision):
        raise ValueError("routing decision contract invalid")
    if (
        decision.schema_version != SYMBOL_ROUTING_SCHEMA_VERSION
        or decision.router_version != SYMBOL_ROUTER_VERSION
        or not isinstance(decision.visual_observation_id, str)
        or not _is_lower_sha256(decision.input_sha256)
        or decision.disposition
        not in {"locally_resolved", "escalate", "block"}
        or not isinstance(decision.requires_confirmation, bool)
    ):
        raise ValueError("routing decision contract invalid")
    if decision.visual_observation_id == "":
        if (
            decision.disposition == "block"
            and decision.local_resolution_reason_codes == ()
            and decision.escalation_reason_codes == ()
            and decision.block_reason_codes
            == ("routing_contract_invalid",)
            and decision.requires_confirmation is True
        ):
            return decision
        raise ValueError("routing decision contract invalid")
    if (
        not decision.visual_observation_id
        or decision.visual_observation_id.strip()
        != decision.visual_observation_id
    ):
        raise ValueError("routing decision contract invalid")

    reason_contract = {
        "locally_resolved": (
            decision.local_resolution_reason_codes,
            LOCAL_RESOLUTION_REASON_CODES,
        ),
        "escalate": (
            decision.escalation_reason_codes,
            ESCALATION_REASON_CODES,
        ),
        "block": (
            decision.block_reason_codes,
            BLOCK_REASON_CODES,
        ),
    }
    reason_arrays = (
        decision.local_resolution_reason_codes,
        decision.escalation_reason_codes,
        decision.block_reason_codes,
    )
    active_reasons, allowed_reasons = reason_contract[
        decision.disposition
    ]
    if (
        any(not isinstance(reasons, tuple) for reasons in reason_arrays)
        or sum(bool(reasons) for reasons in reason_arrays) != 1
        or not _valid_reason_array(active_reasons, allowed_reasons)
        or (
            decision.disposition == "escalate"
            and decision.requires_confirmation is not True
        )
        or (
            decision.disposition == "block"
            and decision.requires_confirmation is not True
        )
    ):
        raise ValueError("routing decision contract invalid")
    return decision


def validate_routing_decision(decision: object) -> RoutingDecision:
    """Contain hostile record fields behind the public contract boundary."""
    try:
        return _validate_routing_decision(decision)
    except Exception as exc:
        raise ValueError("routing decision contract invalid") from exc


def _symbol_routing_identity(
    mode: object,
) -> tuple[SymbolRecognitionMode, str]:
    """Resolve the only runtime-mode to router-version mapping."""
    if not isinstance(mode, str) or mode not in SYMBOL_RECOGNITION_MODES:
        raise ValueError("unsupported symbol recognition mode")
    typed_mode: SymbolRecognitionMode = mode  # type: ignore[assignment]
    return typed_mode, _MODE_ROUTER_VERSION[typed_mode]


def symbol_routing_identity(
    mode: object,
) -> tuple[SymbolRecognitionMode, str]:
    try:
        return _symbol_routing_identity(mode)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("unsupported symbol recognition mode") from exc


def _validate_frozen_symbol_routing_identity(
    mode: object,
    router_version: object,
) -> tuple[SymbolRecognitionMode, str]:
    frozen_mode, expected_version = _symbol_routing_identity(mode)
    if (
        not isinstance(router_version, str)
        or router_version != expected_version
    ):
        raise ValueError("frozen symbol router version does not match mode")
    return frozen_mode, expected_version


def validate_frozen_symbol_routing_identity(
    mode: object,
    router_version: object,
) -> tuple[SymbolRecognitionMode, str]:
    try:
        return _validate_frozen_symbol_routing_identity(
            mode,
            router_version,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "frozen symbol router version does not match mode"
        ) from exc


_MAX_CANONICAL_DEPTH = 16
_MAX_CANONICAL_ITEMS = 1024


def _canonical_value(
    value: object,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> object:
    if depth > _MAX_CANONICAL_DEPTH:
        raise ValueError("canonical value exceeds maximum depth")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimal")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        return value
    if isinstance(value, Mapping):
        current_seen = seen if seen is not None else set()
        identity = id(value)
        if identity in current_seen:
            raise ValueError("cyclic canonical mapping")
        current_seen.add(identity)
        try:
            items: list[tuple[str, object]] = []
            try:
                iterator = iter(value.items())
                for index, pair in enumerate(iterator):
                    if index >= _MAX_CANONICAL_ITEMS:
                        raise ValueError(
                            "canonical mapping exceeds maximum items"
                        )
                    key, item = pair
                    if not isinstance(key, str):
                        raise ValueError("non-string mapping key")
                    items.append((key, item))
            except ValueError:
                raise
            except Exception:
                raise ValueError("canonical mapping unavailable") from None
            return {
                key: _canonical_value(
                    item,
                    depth=depth + 1,
                    seen=current_seen,
                )
                for key, item in sorted(items)
            }
        finally:
            current_seen.remove(identity)
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_CANONICAL_ITEMS:
            raise ValueError("canonical sequence exceeds maximum items")
        current_seen = seen if seen is not None else set()
        identity = id(value)
        if identity in current_seen:
            raise ValueError("cyclic canonical sequence")
        current_seen.add(identity)
        try:
            return [
                _canonical_value(
                    item,
                    depth=depth + 1,
                    seen=current_seen,
                )
                for item in value
            ]
        finally:
            current_seen.remove(identity)
    raise ValueError("unsupported canonical value")


def _projection_evidence(projection: VisualReviewDecision | None) -> object:
    if projection is None:
        return None
    return _canonical_value(
        {
            "observation_id": projection.observation_id,
            "disposition": projection.disposition,
            "source_location_ids": projection.source_location_ids,
            "coordinates": projection.coordinates,
            "candidate_id": projection.candidate_id,
            "existing_candidate_index": projection.existing_candidate_index,
            "candidate_envelope": projection.candidate_envelope,
            "requires_confirmation": projection.requires_confirmation,
            "symbol_kinds": projection.symbol_kinds,
            "rejection_code": projection.rejection_code,
        }
    )


def _input_sha256(resolution: LocalResolution) -> str:
    canonical = json.dumps(
        {
            "visual_observation_id": resolution.visual_observation_id,
            "family_hypotheses": sorted(set(resolution.family_hypotheses)),
            "resolved_family": resolution.resolved_family,
            "reason_codes": sorted(set(resolution.reason_codes)),
            "projection": _projection_evidence(resolution.projection),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _decision(
    resolution: LocalResolution,
    disposition: RoutingDisposition,
    reasons: tuple[str, ...],
    *,
    input_sha256: str,
) -> RoutingDecision:
    return RoutingDecision(
        schema_version=SYMBOL_ROUTING_SCHEMA_VERSION,
        router_version=SYMBOL_ROUTER_VERSION,
        visual_observation_id=resolution.visual_observation_id,
        input_sha256=input_sha256,
        disposition=disposition,
        local_resolution_reason_codes=(
            reasons if disposition == "locally_resolved" else ()
        ),
        escalation_reason_codes=(
            reasons if disposition == "escalate" else ()
        ),
        block_reason_codes=reasons if disposition == "block" else (),
        requires_confirmation=(
            True
            if disposition != "locally_resolved"
            else bool(
                resolution.projection is not None
                and resolution.projection.requires_confirmation
            )
        ),
    )


def _safe_invalid_value(
    value: object,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> object:
    type_name = f"{type(value).__module__}.{type(value).__qualname__}"
    if depth >= 6:
        return {"type": type_name, "truncated": True}
    if value is None:
        return {"type": "builtins.NoneType"}
    if isinstance(value, bool):
        return {"type": "builtins.bool", "value": value}
    if isinstance(value, int):
        return {"type": "builtins.int", "value": value}
    if isinstance(value, float):
        return {
            "type": "builtins.float",
            "value": value if math.isfinite(value) else "nonfinite",
        }
    if isinstance(value, Decimal):
        return {
            "type": "decimal.Decimal",
            "value": str(value) if value.is_finite() else "nonfinite",
        }
    if isinstance(value, str):
        return {
            "type": "builtins.str",
            "length": len(value),
            "sha256": hashlib.sha256(
                value.encode("utf-8", errors="surrogatepass")
            ).hexdigest(),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        content = bytes(value)
        return {
            "type": type_name,
            "length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    if isinstance(value, (tuple, list)):
        current_seen = seen if seen is not None else set()
        identity = id(value)
        if identity in current_seen:
            return {"type": type_name, "cycle": True}
        current_seen.add(identity)
        try:
            return {
                "type": type_name,
                "length": len(value),
                "items": [
                    _safe_invalid_value(
                        item,
                        depth=depth + 1,
                        seen=current_seen,
                    )
                    for item in value[:64]
                ],
            }
        finally:
            current_seen.remove(identity)
    if isinstance(value, Mapping):
        current_seen = seen if seen is not None else set()
        identity = id(value)
        if identity in current_seen:
            return {"type": type_name, "cycle": True}
        current_seen.add(identity)
        try:
            try:
                length = len(value)
                raw_items = []
                for index, pair in enumerate(value.items()):
                    if index >= 64:
                        break
                    raw_items.append(pair)
            except Exception as exc:
                return {
                    "type": type_name,
                    "mapping_error_type": (
                        f"{type(exc).__module__}.{type(exc).__qualname__}"
                    ),
                }
            items = [
                (
                    _safe_invalid_value(
                        key,
                        depth=depth + 1,
                        seen=current_seen,
                    ),
                    _safe_invalid_value(
                        item,
                        depth=depth + 1,
                        seen=current_seen,
                    ),
                )
                for key, item in raw_items
            ]
            items.sort(
                key=lambda pair: json.dumps(
                    pair[0],
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return {
                "type": type_name,
                "length": length,
                "items": items,
            }
        finally:
            current_seen.remove(identity)
    try:
        state = object.__getattribute__(value, "__dict__")
    except Exception:
        state = None
    if isinstance(state, dict):
        state_summary = _safe_invalid_value(
            state,
            depth=depth + 1,
            seen={id(value)} if seen is None else {*seen, id(value)},
        )
        state_sha256 = hashlib.sha256(
            json.dumps(
                state_summary,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return {"type": type_name, "state_sha256": state_sha256}
    return {"type": type_name}


def _safe_projection_summary(value: object) -> object:
    if not isinstance(value, VisualReviewDecision):
        return _safe_invalid_value(value)
    return {
        "type": "VisualReviewDecision",
        "observation_id": _safe_invalid_value(value.observation_id),
        "disposition": _safe_invalid_value(value.disposition),
        "source_location_ids": _safe_invalid_value(
            value.source_location_ids
        ),
        "coordinates": _safe_invalid_value(value.coordinates),
        "candidate_id": _safe_invalid_value(value.candidate_id),
        "existing_candidate_index": _safe_invalid_value(
            value.existing_candidate_index
        ),
        "candidate_envelope": _safe_invalid_value(
            value.candidate_envelope
        ),
        "requires_confirmation": _safe_invalid_value(
            value.requires_confirmation
        ),
        "symbol_kinds": _safe_invalid_value(value.symbol_kinds),
        "rejection_code": _safe_invalid_value(value.rejection_code),
    }


def _invalid_input_sha256(resolution: object) -> str:
    try:
        if isinstance(resolution, LocalResolution):
            summary = {
                "type": "LocalResolution",
                "visual_observation_id": _safe_invalid_value(
                    resolution.visual_observation_id
                ),
                "family_hypotheses": _safe_invalid_value(
                    resolution.family_hypotheses
                ),
                "resolved_family": _safe_invalid_value(
                    resolution.resolved_family
                ),
                "reason_codes": _safe_invalid_value(
                    resolution.reason_codes
                ),
                "projection": _safe_projection_summary(
                    resolution.projection
                ),
            }
        else:
            summary = _safe_invalid_value(resolution)
    except Exception as exc:
        summary = {
            "type": f"{type(resolution).__module__}.{type(resolution).__qualname__}",
            "summary_error_type": (
                f"{type(exc).__module__}.{type(exc).__qualname__}"
            ),
        }
    return hashlib.sha256(
        json.dumps(
            summary,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _contract_invalid(resolution: object) -> RoutingDecision:
    visual_observation_id = ""
    try:
        candidate_id = resolution.visual_observation_id  # type: ignore[union-attr]
        if isinstance(resolution, LocalResolution) and isinstance(
            candidate_id,
            str,
        ) and candidate_id and candidate_id.strip() == candidate_id:
            visual_observation_id = candidate_id
    except Exception:
        pass
    invalid_hash = hashlib.sha256(
        (
            SYMBOL_ROUTING_SCHEMA_VERSION
            + ":"
            + _invalid_input_sha256(resolution)
        ).encode("ascii")
    ).hexdigest()
    return RoutingDecision(
        schema_version=SYMBOL_ROUTING_SCHEMA_VERSION,
        router_version=SYMBOL_ROUTER_VERSION,
        visual_observation_id=visual_observation_id,
        input_sha256=invalid_hash,
        disposition="block",
        local_resolution_reason_codes=(),
        escalation_reason_codes=(),
        block_reason_codes=("routing_contract_invalid",),
        requires_confirmation=True,
    )


def _valid_string_tuple(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and bool(value)
        and all(isinstance(item, str) and bool(item) for item in value)
    )


def _valid_coordinates(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 4
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            for item in value
        )
        and value[2] > value[0]
        and value[3] > value[1]
    )


def _valid_projection(
    resolution: LocalResolution,
    projection: object,
) -> bool:
    if not isinstance(projection, VisualReviewDecision):
        return False
    if (
        not _valid_string_tuple(projection.source_location_ids)
        or not _valid_string_tuple(projection.symbol_kinds)
    ):
        return False
    if (
        projection.observation_id != resolution.visual_observation_id
        or projection.disposition == "ambiguous"
        or projection.rejection_code is not None
        or resolution.resolved_family not in projection.symbol_kinds
        or resolution.visual_observation_id
        not in projection.source_location_ids
        or not set(projection.symbol_kinds).issubset(
            LOCAL_SYMBOL_FAMILIES
        )
        or not _valid_coordinates(projection.coordinates)
        or not isinstance(projection.requires_confirmation, bool)
    ):
        return False
    semantics = _ALLOWED_PROJECTION_SEMANTICS.get(
        resolution.resolved_family
    )
    if (
        semantics is None
        or projection.disposition != semantics[0]
        or projection.symbol_kinds not in semantics[1]
    ):
        return False
    try:
        _projection_evidence(projection)
    except Exception:
        return False
    return True


def _valid_resolution_shape(resolution: object) -> bool:
    if not isinstance(resolution, LocalResolution):
        return False
    if (
        not isinstance(resolution.visual_observation_id, str)
        or not resolution.visual_observation_id
        or resolution.visual_observation_id.strip()
        != resolution.visual_observation_id
        or not _valid_string_tuple(resolution.reason_codes)
        or (
            resolution.resolved_family is not None
            and (
                not isinstance(resolution.resolved_family, str)
                or resolution.resolved_family not in LOCAL_SYMBOL_FAMILIES
                or resolution.resolved_family
                not in resolution.family_hypotheses
            )
        )
    ):
        return False
    if not isinstance(resolution.family_hypotheses, tuple) or any(
        not isinstance(family, str) or not family
        for family in resolution.family_hypotheses
    ):
        return False
    if not resolution.family_hypotheses:
        return (
            resolution.resolved_family is None
            and resolution.projection is None
            and resolution.reason_codes == ("unknown_symbol_pattern",)
        )
    if resolution.resolved_family is None:
        return resolution.projection is None
    return _valid_projection(resolution, resolution.projection)


def _route_visual_observation(
    resolution: object,
) -> RoutingDecision:
    """Choose the exact-one pre-VLM disposition for local resolver evidence."""
    if not _valid_resolution_shape(resolution):
        return _contract_invalid(resolution)
    assert isinstance(resolution, LocalResolution)
    reasons = tuple(sorted(set(resolution.reason_codes)))
    if not reasons:
        return _contract_invalid(resolution)

    reason_set = set(reasons)
    if reason_set.issubset(LOCAL_RESOLUTION_REASON_CODES):
        has_family_reason = bool(
            reason_set
            & {
                "native_symbol_explicit",
                "deterministic_geometry_complete",
            }
        )
        if (
            resolution.resolved_family is None
            or resolution.projection is None
            or "local_projection_complete" not in reason_set
            or not has_family_reason
        ):
            return _contract_invalid(resolution)
        return _decision(
            resolution,
            "locally_resolved",
            reasons,
            input_sha256=_input_sha256(resolution),
        )

    if reason_set.issubset(ESCALATION_REASON_CODES):
        if (
            resolution.resolved_family is not None
            or resolution.projection is not None
        ):
            return _contract_invalid(resolution)
        return _decision(
            resolution,
            "escalate",
            reasons,
            input_sha256=_input_sha256(resolution),
        )

    if reason_set.issubset(BLOCK_REASON_CODES):
        if (
            resolution.resolved_family is not None
            or resolution.projection is not None
        ):
            return _contract_invalid(resolution)
        return _decision(
            resolution,
            "block",
            reasons,
            input_sha256=_input_sha256(resolution),
        )

    return _contract_invalid(resolution)


def route_visual_observation(
    resolution: object,
) -> RoutingDecision:
    """Choose one disposition and fail closed on hostile local evidence."""
    try:
        return _route_visual_observation(resolution)
    except Exception:
        return _contract_invalid(resolution)
