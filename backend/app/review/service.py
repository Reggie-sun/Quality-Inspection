from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.complex_fallback import CoarseType
from app.candidates.confidence import (
    ConfidenceDecisionContractError,
    validate_confidence_decision,
)
from app.candidates.models import AutomaticResult
from app.candidates.schemas import Candidate, stable_candidate_id
from app.config import get_settings
from app.projects.models import Project
from app.projects.state import ProjectState, transition
from app.review.locks import require_active_lock
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.review.schemas import (
    Add,
    Edit,
    Exclude,
    GenerateSipTable,
    IgnoreSource,
    IgnoreSources,
    Keep,
    Merge,
    PromoteSource,
    ResolveConfirmation,
    ReviewCommand,
    SetBalloonRequired,
    SetSipDetailFields,
    SetSipMetadata,
    SetTechnicalRequirementMatch,
    SIP_DETAIL_FIELDS,
    SIP_METADATA_FIELDS,
    SIP_OPTIONAL_DETAIL_FIELDS,
    Split,
    parse_review_command,
    validate_edit_fields,
)
from app.review.sip_mapping import RULE_VERSION as SIP_MAPPING_RULE_VERSION
from app.review.sip_mapping import map_sip_item
from app.storage.local import LocalFileStorage


class ReviewNotFound(LookupError):
    pass


class ReviewVersionConflict(RuntimeError):
    pass


class FreezeBlocked(RuntimeError):
    def __init__(self, blockers: list[str]) -> None:
        self.blockers = tuple(blockers)
        self.code = blockers[0]
        super().__init__(f"review item set cannot be frozen: {', '.join(blockers)}")


class ItemsFrozen(RuntimeError):
    pass


class ReviewConfirmationBlocked(RuntimeError):
    def __init__(self, blockers: list[str]) -> None:
        self.blockers = tuple(blockers)
        self.code = blockers[0]
        super().__init__(f"review confirmation blocked: {', '.join(blockers)}")


class ReviewedResultImmutable(RuntimeError):
    pass


_COORDINATES = TypeAdapter(tuple[float, float, float, float])
_COARSE_TYPE = TypeAdapter(CoarseType)
_SIP_DETAIL_CONFIRMED = "sip_detail_fields_confirmed"


def manual_review_count(
    items: object,
    coverage: object,
) -> int:
    item_values = items if isinstance(items, list) else []
    review_item_ids = {
        item.get("item_id")
        for item in item_values
        if isinstance(item, dict)
        and item.get("active", True)
        and item.get("requires_confirmation") is True
        and isinstance(item.get("item_id"), str)
    }
    entries = coverage.get("entries", []) if isinstance(coverage, dict) else []
    source_only_ids = {
        entry.get("observation_id")
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("requires_confirmation") is True
        and entry.get("candidate_id") is None
        and isinstance(entry.get("observation_id"), str)
    } if isinstance(entries, list) else set()
    return len(review_item_ids) + len(source_only_ids)


class ReviewService:
    def __init__(
        self,
        session: Session,
        *,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self.session = session
        self.storage = storage

    def create_from_raw(self, raw_result_id: uuid.UUID) -> ReviewWorkingCopy:
        existing = self.session.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.raw_result_id == raw_result_id
            )
        )
        if existing is not None:
            return existing

        raw_result = self.session.get(AutomaticResult, raw_result_id)
        if raw_result is None:
            raise ReviewNotFound(f"automatic result {raw_result_id} was not found")
        project = self.session.scalar(
            select(Project)
            .where(Project.id == raw_result.project_id)
            .with_for_update()
        )
        if project is None:
            raise ReviewNotFound(f"project {raw_result.project_id} was not found")

        current_state = ProjectState(project.state)
        if current_state == ProjectState.READY_FOR_EDIT:
            project.state = transition(current_state, ProjectState.EDITING)
        elif current_state != ProjectState.EDITING:
            raise ValueError(f"project {project.id} is not ready for review")

        items = [
            self._current_item(candidate, raw_result.schema_version)
            for candidate in raw_result.candidates
        ]
        technical_requirements = copy.deepcopy(
            raw_result.technical_requirements
        )
        self._project_technical_requirements(
            technical_requirements,
            items,
        )
        working = ReviewWorkingCopy(
            project_id=raw_result.project_id,
            raw_result_id=raw_result.id,
            version=1,
            items=items,
            coverage=self._review_coverage(raw_result.coverage),
            technical_requirements=technical_requirements,
            sip_metadata={},
            numbering_stale=False,
        )
        self.session.add(working)
        self.session.commit()
        self.session.refresh(working)
        return working

    def apply(
        self,
        working_copy_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
        command: dict[str, object],
    ) -> ReviewWorkingCopy:
        operator_id = self._operator_id(operator_id)
        parsed = parse_review_command(command)
        working = self.session.get(ReviewWorkingCopy, working_copy_id)
        if working is None:
            raise ReviewNotFound(f"working copy {working_copy_id} was not found")
        require_active_lock(self.session, working.project_id, operator_id)
        if working.version != expected_version:
            self.session.rollback()
            raise ReviewVersionConflict(
                f"expected review version {expected_version}, found {working.version}"
            )
        if working.items_frozen_at is not None:
            self.session.rollback()
            raise ItemsFrozen("review item set is frozen")

        items = copy.deepcopy(working.items)
        coverage = copy.deepcopy(working.coverage)
        technical_requirements = copy.deepcopy(
            working.technical_requirements
        )
        sip_metadata = copy.deepcopy(working.sip_metadata)
        needs_sip_source_pages = (
            isinstance(parsed, GenerateSipTable)
            and any(
                item.get("active", True)
                and not self._sip_fields_are_manual(item)
                and not isinstance(item.get("page_index"), int)
                for item in items
            )
        )
        sip_source_pages = (
            self._sip_source_page_indices(working)
            if needs_sip_source_pages
            else {}
        )
        target_ids, numbering_stale = self._apply_command(
            items,
            coverage,
            technical_requirements,
            sip_metadata,
            parsed,
            numbering_stale=working.numbering_stale,
            sip_source_pages=sip_source_pages,
        )
        self._validate_requirement_target_invariants(
            items,
            technical_requirements,
        )
        before_version = working.version
        after_version = before_version + 1
        updated_id = self.session.execute(
            update(ReviewWorkingCopy)
            .where(
                ReviewWorkingCopy.id == working_copy_id,
                ReviewWorkingCopy.version == expected_version,
                ReviewWorkingCopy.items_frozen_at.is_(None),
            )
            .values(
                items=items,
                coverage=coverage,
                technical_requirements=technical_requirements,
                sip_metadata=sip_metadata,
                numbering_stale=numbering_stale,
                version=after_version,
            )
            .returning(ReviewWorkingCopy.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if updated_id is None:
            self.session.rollback()
            raise ReviewVersionConflict("review working copy changed concurrently")
        self.session.add(
            OperationRecord(
                project_id=working.project_id,
                operator_id=operator_id,
                command=parsed.type,
                target_ids=target_ids,
                before_version=before_version,
                after_version=after_version,
            )
        )
        self.session.commit()
        self.session.expire_all()
        saved = self.session.get(ReviewWorkingCopy, updated_id)
        if saved is None:
            raise ReviewNotFound(f"working copy {updated_id} was not found after save")
        return saved

    def get_working_copy(self, working_copy_id: uuid.UUID) -> ReviewWorkingCopy:
        working = self.session.get(ReviewWorkingCopy, working_copy_id)
        if working is None:
            raise ReviewNotFound(f"working copy {working_copy_id} was not found")
        return working

    def get_for_project(self, project_id: uuid.UUID) -> ReviewWorkingCopy:
        working = self.session.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == project_id
            )
        )
        if working is None:
            raise ReviewNotFound(f"working copy for project {project_id} was not found")
        return working

    def freeze_items(
        self,
        working_copy_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
    ) -> ReviewWorkingCopy:
        operator_id = self._operator_id(operator_id)
        working = self.session.get(ReviewWorkingCopy, working_copy_id)
        if working is None:
            raise ReviewNotFound(f"working copy {working_copy_id} was not found")
        require_active_lock(self.session, working.project_id, operator_id)
        if working.version != expected_version:
            self.session.rollback()
            raise ReviewVersionConflict(
                f"expected review version {expected_version}, found {working.version}"
            )
        if working.items_frozen_at is not None:
            self.session.rollback()
            raise ItemsFrozen("review item set is already frozen")

        blockers = self.freeze_blockers(
            working.items,
            working.coverage,
            working.sip_metadata,
        )
        if blockers:
            self.session.rollback()
            raise FreezeBlocked(blockers)
        frozen_at = self.session.scalar(select(func.now()))
        if frozen_at is None:
            self.session.rollback()
            raise RuntimeError("PostgreSQL database clock was unavailable")
        updated_id = self.session.execute(
            update(ReviewWorkingCopy)
            .where(
                ReviewWorkingCopy.id == working_copy_id,
                ReviewWorkingCopy.version == expected_version,
                ReviewWorkingCopy.items_frozen_at.is_(None),
            )
            .values(
                items_frozen_at=frozen_at,
                items_frozen_by=operator_id,
                items_frozen_version=expected_version,
            )
            .returning(ReviewWorkingCopy.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if updated_id is None:
            self.session.rollback()
            raise ReviewVersionConflict("review working copy changed concurrently")
        self.session.commit()
        self.session.expire_all()
        frozen = self.session.get(ReviewWorkingCopy, updated_id)
        if frozen is None:
            raise ReviewNotFound(f"working copy {updated_id} was not found after freeze")
        return frozen

    @staticmethod
    def freeze_blockers(
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        sip_metadata: dict[str, Any],
    ) -> list[str]:
        blockers: list[str] = []
        if coverage.get("blocking_count", 0):
            blockers.append("coverage_blocking")
        unresolved_item = any(
            item.get("active", True) and item.get("requires_confirmation")
            for item in items
        )
        unresolved_coverage = any(
            entry.get("requires_confirmation")
            for entry in coverage.get("entries", [])
        )
        sip_unconfirmed = bool(
            ReviewService._sip_confirmation_blockers(items, sip_metadata)
        )
        if unresolved_item or unresolved_coverage or sip_unconfirmed:
            blockers.append("unresolved_confirmation")
        if any(
            item.get("active", True) and item.get("balloon_required") is None
            for item in items
        ):
            blockers.append("balloon_required_unconfirmed")
        return blockers

    def reviewed_result_for(self, project_id: uuid.UUID) -> ReviewedResult | None:
        return self.session.scalar(
            select(ReviewedResult).where(ReviewedResult.project_id == project_id)
        )

    def confirm(
        self,
        working_copy_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
    ) -> ReviewedResult:
        from app.balloons.models import Balloon
        from app.balloons.service import BalloonService

        operator_id = self._operator_id(operator_id)
        preview = self.session.get(ReviewWorkingCopy, working_copy_id)
        if preview is None:
            raise ReviewNotFound(f"working copy {working_copy_id} was not found")
        require_active_lock(self.session, preview.project_id, operator_id)
        working = self.session.scalar(
            select(ReviewWorkingCopy)
            .where(ReviewWorkingCopy.id == working_copy_id)
            .with_for_update()
        )
        if working is None:
            raise ReviewNotFound(f"working copy {working_copy_id} was not found")
        if working.version != expected_version:
            self.session.rollback()
            raise ReviewVersionConflict(
                f"expected review version {expected_version}, found {working.version}"
            )
        if working.items_frozen_at is None:
            self.session.rollback()
            raise FreezeBlocked(["item_set_not_frozen"])

        existing = self.session.scalar(
            select(ReviewedResult).where(
                ReviewedResult.working_copy_id == working.id,
                ReviewedResult.working_version == working.version,
            )
        )
        if existing is not None:
            return existing
        if working.numbering_stale:
            self.session.rollback()
            raise ReviewConfirmationBlocked(["numbering_stale"])
        sip_blockers = self._sip_confirmation_blockers(
            working.items,
            working.sip_metadata,
        )
        if sip_blockers:
            self.session.rollback()
            raise ReviewConfirmationBlocked(sip_blockers)

        balloons = list(
            self.session.scalars(
                select(Balloon)
                .where(
                    Balloon.project_id == working.project_id,
                    Balloon.status == "active",
                )
                .order_by(Balloon.sort_order, Balloon.id)
                .with_for_update()
            )
        )
        balloon_service = BalloonService(
            self.session,
            storage=self.storage,
        )
        blockers = balloon_service.validation_blockers(working.project_id)
        if blockers:
            self.session.rollback()
            raise ReviewConfirmationBlocked(blockers)

        project = self.session.scalar(
            select(Project).where(Project.id == working.project_id).with_for_update()
        )
        if project is None:
            self.session.rollback()
            raise ReviewNotFound(f"project {working.project_id} was not found")
        project.state = transition(ProjectState(project.state), ProjectState.REVIEWED)
        reviewed = ReviewedResult(
            project_id=working.project_id,
            working_copy_id=working.id,
            working_version=working.version,
            items=[
                copy.deepcopy(item)
                for item in working.items
                if item.get("active", True)
            ],
            balloons=[balloon.snapshot() for balloon in balloons],
            sip_metadata=copy.deepcopy(working.sip_metadata),
            schema_version="reviewed-result/2",
        )
        self.session.add(reviewed)
        self.session.flush()
        self.session.add(
            OperationRecord(
                project_id=working.project_id,
                operator_id=operator_id,
                command="confirm_reviewed_result",
                target_ids=[str(reviewed.id)],
                before_version=working.version,
                after_version=working.version,
            )
        )
        self.session.commit()
        self.session.refresh(reviewed)
        return reviewed

    def replace_items(
        self,
        reviewed_result_id: uuid.UUID,
        _: list[dict[str, Any]],
    ) -> None:
        reviewed = self.session.get(ReviewedResult, reviewed_result_id)
        if reviewed is None:
            raise ReviewNotFound(
                f"reviewed result {reviewed_result_id} was not found"
            )
        raise ReviewedResultImmutable("immutable reviewed result cannot be replaced")

    @staticmethod
    def _current_item(
        candidate: dict[str, Any],
        raw_schema_version: str,
    ) -> dict[str, Any]:
        item_id = str(candidate["candidate_id"])
        payload = copy.deepcopy(candidate["payload"])
        payload.pop("candidate_id", None)
        payload.pop("confidence_decision", None)
        validated_decision = None
        if raw_schema_version == "automatic-result/2":
            try:
                validated_decision = validate_confidence_decision(
                    candidate.get("confidence_decision")
                )
            except ConfidenceDecisionContractError:
                pass
        is_auto_accepted = (
            validated_decision is not None
            and validated_decision.review_disposition == "auto_accepted"
        )
        current = {
            "item_id": item_id,
            **payload,
            "source_location_ids": list(candidate.get("source_location_ids", [])),
            "source_type": "automatic",
            "status": "auto_accepted" if is_auto_accepted else "pending",
            "requires_confirmation": not is_auto_accepted,
            "acceptance_source": (
                "confidence_policy" if is_auto_accepted else None
            ),
            "active": True,
        }
        refs = candidate.get("technical_requirement_refs")
        if isinstance(refs, list) and all(isinstance(ref, str) for ref in refs):
            current["technical_requirement_refs"] = list(refs)
        if validated_decision is not None:
            current["confidence_decision"] = copy.deepcopy(
                candidate["confidence_decision"]
            )
        return current

    @staticmethod
    def _review_coverage(raw_coverage: dict[str, Any]) -> dict[str, Any]:
        coverage = copy.deepcopy(raw_coverage)
        for entry in coverage.get("entries", []):
            if isinstance(entry, dict):
                advisor_review = entry.get("advisor_review")
                legacy_fields = {
                    "route",
                    "schema_version",
                    "symbol_kinds",
                    "rejection_code",
                }
                active_fields = {*legacy_fields, "confidence_signal"}
                if (
                    isinstance(advisor_review, dict)
                    and (
                        (
                            set(advisor_review) == legacy_fields
                            and advisor_review.get("schema_version")
                            == "visual-symbol-review/1"
                        )
                        or (
                            set(advisor_review) == active_fields
                            and advisor_review.get("schema_version")
                            == "visual-symbol-review/2"
                        )
                    )
                    and advisor_review.get("route") == "visual_symbol"
                ):
                    symbol_kinds = advisor_review.get("symbol_kinds")
                    rejection_code = advisor_review.get("rejection_code")
                    if (
                        isinstance(symbol_kinds, list)
                        and all(
                            isinstance(symbol_kind, str)
                            for symbol_kind in symbol_kinds
                        )
                    ):
                        entry["symbol_kinds"] = list(symbol_kinds)
                    if rejection_code is None or isinstance(
                        rejection_code,
                        str,
                    ):
                        entry["rejection_code"] = rejection_code
                entry.pop("advisor_review", None)
        return coverage

    def _apply_command(
        self,
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        technical_requirements: list[dict[str, Any]],
        sip_metadata: dict[str, Any],
        command: ReviewCommand,
        *,
        numbering_stale: bool,
        sip_source_pages: dict[str, int],
    ) -> tuple[list[str], bool]:
        if isinstance(command, Keep):
            item = self._active_item(items, command.item_id)
            self._complete_manual_item(item, coverage, accepted=True)
            return [command.item_id], numbering_stale
        if isinstance(command, Exclude):
            item = self._active_item(items, command.item_id)
            self._complete_manual_item(item, coverage, accepted=False)
            self._remap_requirement_targets(
                items,
                coverage,
                technical_requirements,
                {command.item_id: ()},
            )
            return [command.item_id], True
        if isinstance(command, Edit):
            item = self._active_item(items, command.item_id)
            self._edit_item(item, command.fields)
            self._clear_sip_detail_fields(item)
            self._complete_manual_item(item, coverage, accepted=True)
            return [command.item_id], numbering_stale or "coordinates" in command.fields
        if isinstance(command, Add):
            item_id = str(uuid.uuid4())
            source_location_ids = (
                [f"manual:{item_id}"] if command.page_index is not None else []
            )
            items.append(
                {
                    "item_id": item_id,
                    "item_type": command.item_type,
                    "raw_text": command.raw_text,
                    "normalized_text": command.raw_text,
                    "coordinates": list(command.coordinates),
                    "scope": command.scope,
                    "balloon_required": command.balloon_required,
                    "requires_confirmation": False,
                    "source_location_ids": source_location_ids,
                    "page_index": command.page_index,
                    "source_type": "manual",
                    "status": "kept",
                    "acceptance_source": "manual",
                    "active": True,
                }
            )
            return [item_id], True
        if isinstance(command, Merge):
            if len(set(command.item_ids)) != len(command.item_ids):
                raise ValueError("merge item IDs must be distinct")
            source_items = [self._active_item(items, item_id) for item_id in command.item_ids]
            item_type = source_items[0].get("item_type")
            if item_type is None or any(
                source.get("item_type") != item_type for source in source_items
            ):
                raise ValueError("merge requires the same simple item type")
            global_target_ids = {
                requirement.get("generated_candidate_id")
                for requirement in technical_requirements
                if requirement.get("match_outcome") == "global_scope"
            }
            if any(
                item_id in global_target_ids
                for item_id in command.item_ids
            ) and any(
                source.get("scope") != "global_requirement"
                or source.get("balloon_required") is not False
                for source in source_items
            ):
                raise ValueError(
                    "global requirement merge requires global unnumbered items"
                )
            merged_id = str(uuid.uuid4())
            merged = copy.deepcopy(source_items[0])
            self._clear_sip_detail_fields(merged)
            merged.update(
                {
                    "item_id": merged_id,
                    "raw_text": command.raw_text,
                    "normalized_text": command.raw_text,
                    "quantity": None,
                    "source_location_ids": self._ordered_source_union(source_items),
                    "source_type": "manual",
                    "status": "kept",
                    "requires_confirmation": False,
                    "confirmation_accepted": True,
                    "acceptance_source": "manual_override",
                    "active": True,
                    "merged_from_item_ids": list(command.item_ids),
                }
            )
            merged.pop("confidence_decision", None)
            for source in source_items:
                self._complete_manual_item(source, coverage, accepted=True)
                source["status"] = "superseded"
                source["active"] = False
            items.append(merged)
            self._remap_requirement_targets(
                items,
                coverage,
                technical_requirements,
                {
                    source_id: (merged_id,)
                    for source_id in command.item_ids
                },
            )
            return [*command.item_ids, merged_id], True
        if isinstance(command, Split):
            source = self._active_item(items, command.item_id)
            if "item_type" not in source:
                raise ValueError("split is limited to simple items")
            self._complete_manual_item(source, coverage, accepted=True)
            source["status"] = "superseded"
            source["active"] = False
            split_ids: list[str] = []
            for part in command.parts:
                split_id = str(uuid.uuid4())
                split_ids.append(split_id)
                split_item = copy.deepcopy(source)
                self._clear_sip_detail_fields(split_item)
                split_item.update(
                    {
                        "item_id": split_id,
                        "raw_text": part.raw_text,
                        "normalized_text": part.raw_text,
                        "quantity": None,
                        "source_type": "manual",
                        "status": "kept",
                        "requires_confirmation": False,
                        "confirmation_accepted": True,
                        "acceptance_source": "manual_override",
                        "active": True,
                        "split_from_item_id": command.item_id,
                    }
                )
                split_item.pop("confidence_decision", None)
                items.append(split_item)
            self._remap_requirement_targets(
                items,
                coverage,
                technical_requirements,
                {command.item_id: tuple(split_ids)},
            )
            return [command.item_id, *split_ids], True
        if isinstance(command, PromoteSource):
            entry = self._pending_source_entry(
                coverage,
                command.observation_id,
            )
            source_location_id = entry.get("source_location_id")
            if (
                not isinstance(source_location_id, str)
                or not source_location_id.strip()
            ):
                raise ReviewNotFound(
                    f"source location for {command.observation_id} was not found"
                )
            coordinates = entry.get("coordinates")
            if (
                not isinstance(coordinates, (list, tuple))
                or len(coordinates) != 4
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    for value in coordinates
                )
            ):
                raise ReviewNotFound(
                    f"source coordinates for {command.observation_id} were not found"
                )
            item_id = str(uuid.uuid4())
            items.append(
                {
                    "item_id": item_id,
                    "item_type": command.item_type,
                    "raw_text": command.raw_text,
                    "normalized_text": command.raw_text,
                    "coordinates": list(coordinates),
                    "scope": command.scope,
                    "balloon_required": command.balloon_required,
                    "requires_confirmation": False,
                    "source_location_ids": [source_location_id],
                    "page_index": command.page_index,
                    "source_type": "manual",
                    "status": "kept",
                    "acceptance_source": "manual",
                    "active": True,
                }
            )
            entry.update(
                {
                    "disposition": "candidate",
                    "candidate_id": item_id,
                    "requires_confirmation": False,
                    "confirmation_accepted": True,
                }
            )
            self._refresh_review_required_count(coverage)
            return [command.observation_id, item_id], True
        if isinstance(command, IgnoreSource):
            entry = self._pending_source_entry(
                coverage,
                command.observation_id,
            )
            entry.update(
                {
                    "disposition": "non_inspection",
                    "candidate_id": None,
                    "requires_confirmation": False,
                    "confirmation_accepted": False,
                }
            )
            self._refresh_review_required_count(coverage)
            return [command.observation_id], numbering_stale
        if isinstance(command, IgnoreSources):
            entries = [
                self._pending_source_entry(coverage, observation_id)
                for observation_id in command.observation_ids
            ]
            for entry in entries:
                entry.update(
                    {
                        "disposition": "non_inspection",
                        "candidate_id": None,
                        "requires_confirmation": False,
                        "confirmation_accepted": False,
                    }
                )
            self._refresh_review_required_count(coverage)
            return list(command.observation_ids), numbering_stale
        if isinstance(command, ResolveConfirmation):
            self._resolve_confirmation(
                items,
                coverage,
                command.item_id,
                command.accepted,
            )
            if not command.accepted:
                self._remap_requirement_targets(
                    items,
                    coverage,
                    technical_requirements,
                    {command.item_id: ()},
                )
            return [command.item_id], numbering_stale or not command.accepted
        if isinstance(command, SetBalloonRequired):
            item = self._active_item(items, command.item_id)
            item["balloon_required"] = command.balloon_required
            self._complete_manual_item(item, coverage, accepted=True)
            return [command.item_id], True
        if isinstance(command, SetSipDetailFields):
            item = self._active_item(items, command.item_id)
            values = command.model_dump(mode="json")
            for field in (*SIP_DETAIL_FIELDS, *SIP_OPTIONAL_DETAIL_FIELDS):
                item[field] = values[field]
            item[_SIP_DETAIL_CONFIRMED] = True
            item.pop("sip_suggestion_provenance", None)
            item.pop("sip_mapping_exceptions", None)
            return [command.item_id], numbering_stale
        if isinstance(command, GenerateSipTable):
            target_ids: list[str] = []
            for item in items:
                if not item.get("active", True):
                    continue
                target_ids.append(str(item["item_id"]))
                if self._sip_fields_are_manual(item):
                    continue
                mapping_item = item
                if not isinstance(item.get("page_index"), int):
                    page_index = next(
                        (
                            sip_source_pages[str(source_id)]
                            for source_id in item.get("source_location_ids", [])
                            if str(source_id) in sip_source_pages
                        ),
                        None,
                    )
                    if page_index is not None:
                        mapping_item = {**item, "page_index": page_index}
                result = map_sip_item(
                    mapping_item,
                    inspection_role=command.inspection_role,
                )
                for field in (*SIP_DETAIL_FIELDS, *SIP_OPTIONAL_DETAIL_FIELDS):
                    if field in result.fields:
                        item[field] = result.fields[field]
                    else:
                        item.pop(field, None)
                item["sip_suggestion_provenance"] = result.provenance
                item["sip_mapping_exceptions"] = list(result.exceptions)
                item[_SIP_DETAIL_CONFIRMED] = not result.exceptions
            return target_ids, numbering_stale
        if isinstance(command, SetTechnicalRequirementMatch):
            return self._set_technical_requirement_match(
                items,
                coverage,
                technical_requirements,
                command,
                numbering_stale=numbering_stale,
            )
        if isinstance(command, SetSipMetadata):
            values = command.model_dump(mode="json")
            sip_metadata.clear()
            sip_metadata.update(
                {field: values[field] for field in SIP_METADATA_FIELDS}
            )
            return ["sip_metadata"], numbering_stale
        raise AssertionError(f"unsupported review command: {command.type}")

    @staticmethod
    def _active_item(
        items: list[dict[str, Any]],
        item_id: str,
    ) -> dict[str, Any]:
        for item in items:
            if item["item_id"] == item_id and item.get("active", True):
                return item
        raise ReviewNotFound(f"active review item {item_id} was not found")

    @staticmethod
    def _project_technical_requirements(
        technical_requirements: list[dict[str, Any]],
        items: list[dict[str, Any]],
    ) -> None:
        item_by_id = {
            str(item["item_id"]): item
            for item in items
            if isinstance(item.get("item_id"), str)
        }
        for requirement in technical_requirements:
            requirement_id = requirement.get("requirement_id")
            if not isinstance(requirement_id, str):
                continue
            requirement.setdefault("review_status", "suggested")
            target_ids = list(requirement.get("matched_candidate_ids", []))
            generated_id = requirement.get("generated_candidate_id")
            if isinstance(generated_id, str):
                target_ids.append(generated_id)
            for target_id in target_ids:
                item = item_by_id.get(str(target_id))
                if item is None:
                    continue
                ReviewService._add_requirement_ref(item, requirement_id)
                ReviewService._apply_requirement_suggestion(
                    item,
                    requirement,
                )

    @staticmethod
    def _validate_requirement_target_invariants(
        items: list[dict[str, Any]],
        technical_requirements: list[dict[str, Any]],
    ) -> None:
        active_items = {
            str(item["item_id"]): item
            for item in items
            if isinstance(item.get("item_id"), str)
            and item.get("active", True)
        }
        for item in active_items.values():
            if (
                item.get("scope") == "global_requirement"
                and item.get("balloon_required") is not False
            ):
                raise ValueError(
                    "global requirement target must remain global and unnumbered"
                )
        for requirement in technical_requirements:
            if requirement.get("match_outcome") != "global_scope":
                continue
            generated_id = requirement.get("generated_candidate_id")
            target = (
                active_items.get(generated_id)
                if isinstance(generated_id, str)
                else None
            )
            if (
                target is None
                or target.get("scope") != "global_requirement"
                or target.get("balloon_required") is not False
            ):
                raise ValueError(
                    "global requirement target must remain global and unnumbered"
                )

    @staticmethod
    def _add_requirement_ref(
        item: dict[str, Any],
        requirement_id: str,
    ) -> None:
        refs = item.setdefault("technical_requirement_refs", [])
        if not isinstance(refs, list):
            refs = []
        item["technical_requirement_refs"] = sorted(
            {
                ref
                for ref in [*refs, requirement_id]
                if isinstance(ref, str)
            }
        )

    @staticmethod
    def _apply_requirement_suggestion(
        item: dict[str, Any],
        requirement: dict[str, Any],
    ) -> None:
        if ReviewService._sip_fields_are_manual(item):
            return
        if item.get(_SIP_DETAIL_CONFIRMED) is True:
            ReviewService._clear_automatic_sip_fields(item)
        suggestion = requirement.get("sip_suggestion")
        requirement_id = requirement.get("requirement_id")
        if not isinstance(suggestion, dict) or not isinstance(
            requirement_id,
            str,
        ):
            return
        provenance = item.setdefault("sip_suggestion_provenance", {})
        if not isinstance(provenance, dict):
            provenance = {}
            item["sip_suggestion_provenance"] = provenance
        for field in (
            "inspection_item",
            "inspection_standard",
            "key_dimension",
            "source_page",
            "remarks",
        ):
            value = suggestion.get(field)
            if value is None or item.get(field) not in (None, ""):
                continue
            item[field] = copy.deepcopy(value)
            provenance[field] = requirement_id
        item.setdefault(_SIP_DETAIL_CONFIRMED, False)

    @staticmethod
    def _requirement(
        technical_requirements: list[dict[str, Any]],
        requirement_id: str,
    ) -> dict[str, Any]:
        matches = [
            requirement
            for requirement in technical_requirements
            if requirement.get("requirement_id") == requirement_id
        ]
        if len(matches) != 1:
            raise ReviewNotFound(
                f"technical requirement {requirement_id} was not found"
            )
        return matches[0]

    @staticmethod
    def _remove_requirement_projection(
        items: list[dict[str, Any]],
        requirement_id: str,
    ) -> None:
        generated_id = stable_candidate_id(
            "technical-requirement-candidate",
            requirement_id,
        )
        for item in items:
            refs = item.get("technical_requirement_refs")
            if isinstance(refs, list):
                item["technical_requirement_refs"] = [
                    ref for ref in refs if ref != requirement_id
                ]
            provenance = item.get("sip_suggestion_provenance")
            if (
                isinstance(provenance, dict)
                and not ReviewService._sip_fields_are_manual(item)
            ):
                removed_projection = False
                for field, source_requirement_id in list(provenance.items()):
                    if source_requirement_id != requirement_id:
                        continue
                    item.pop(field, None)
                    provenance.pop(field, None)
                    removed_projection = True
                if not provenance:
                    item.pop("sip_suggestion_provenance", None)
                if removed_projection and item.get("active", True):
                    item[_SIP_DETAIL_CONFIRMED] = False
                    exceptions = item.get("sip_mapping_exceptions")
                    normalized_exceptions = (
                        [
                            str(exception)
                            for exception in exceptions
                            if isinstance(exception, str)
                        ]
                        if isinstance(exceptions, list)
                        else []
                    )
                    if "sip_regeneration_required" not in normalized_exceptions:
                        normalized_exceptions.append("sip_regeneration_required")
                    item["sip_mapping_exceptions"] = normalized_exceptions
            if item.get("item_id") == generated_id:
                item["active"] = False
                item["status"] = "superseded"

    def _remap_requirement_targets(
        self,
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        technical_requirements: list[dict[str, Any]],
        replacements: dict[str, tuple[str, ...]],
    ) -> None:
        active_items = {
            str(item["item_id"]): item
            for item in items
            if isinstance(item.get("item_id"), str)
            and item.get("active", True)
        }
        for requirement in technical_requirements:
            match_outcome = requirement.get("match_outcome")
            if match_outcome == "matched_items":
                current_ids = requirement.get("matched_candidate_ids")
                if not isinstance(current_ids, list):
                    continue
            elif match_outcome == "global_scope":
                generated_id = requirement.get("generated_candidate_id")
                if not isinstance(generated_id, str):
                    continue
                current_ids = [generated_id]
            else:
                continue
            if not any(
                target_id in replacements for target_id in current_ids
            ):
                continue
            requirement_id = requirement.get("requirement_id")
            if not isinstance(requirement_id, str):
                continue
            remapped_ids = sorted(
                {
                    remapped_id
                    for target_id in current_ids
                    for remapped_id in replacements.get(
                        target_id,
                        (target_id,),
                    )
                }
            )
            self._remove_requirement_projection(items, requirement_id)
            if not remapped_ids or (
                match_outcome == "global_scope"
                and len(remapped_ids) != 1
            ):
                requirement.update(
                    {
                        "match_outcome": "unresolved",
                        "matched_candidate_ids": [],
                        "generated_candidate_id": None,
                        "review_required": True,
                        "review_status": "suggested",
                    }
                )
                self._sync_requirement_coverage(
                    coverage,
                    technical_requirements,
                    requirement,
                )
                continue
            if match_outcome == "global_scope":
                requirement.update(
                    {
                        "matched_candidate_ids": [],
                        "generated_candidate_id": remapped_ids[0],
                    }
                )
            else:
                requirement["matched_candidate_ids"] = remapped_ids
            for target_id in remapped_ids:
                target = active_items.get(target_id)
                if target is None:
                    raise ReviewNotFound(
                        f"active review item {target_id} was not found"
                    )
                self._add_requirement_ref(target, requirement_id)
                self._apply_requirement_suggestion(target, requirement)
            self._sync_requirement_coverage(
                coverage,
                technical_requirements,
                requirement,
            )

    @staticmethod
    def _sync_requirement_coverage(
        coverage: dict[str, Any],
        technical_requirements: list[dict[str, Any]],
        requirement: dict[str, Any],
    ) -> None:
        source_ids = set(requirement.get("source_location_ids", []))
        for entry in ReviewService._coverage_entries(coverage):
            observation_id = entry.get("observation_id")
            if observation_id not in source_ids:
                continue
            source_requirements = [
                candidate
                for candidate in technical_requirements
                if observation_id in candidate.get("source_location_ids", [])
            ]
            requires_confirmation = any(
                candidate.get("review_required") is True
                for candidate in source_requirements
            )
            entry["requires_confirmation"] = requires_confirmation
            if requires_confirmation:
                entry.pop("confirmation_accepted", None)
            else:
                entry["confirmation_accepted"] = any(
                    candidate.get("review_status") == "confirmed"
                    for candidate in source_requirements
                )
        ReviewService._refresh_review_required_count(coverage)

    @staticmethod
    def _global_requirement_item(
        items: list[dict[str, Any]],
        requirement: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = str(requirement["requirement_id"])
        item_id = stable_candidate_id(
            "technical-requirement-candidate",
            requirement_id,
        )
        for item in items:
            if item.get("item_id") == item_id:
                item["active"] = True
                item["status"] = "pending"
                return item
        coordinates = requirement.get("coordinates")
        coordinate = (
            list(coordinates[0])
            if isinstance(coordinates, list) and coordinates
            else None
        )
        item = {
            "item_id": item_id,
            "item_type": "general_requirement",
            "raw_text": requirement.get("raw_text", ""),
            "normalized_text": requirement.get("normalized_text", ""),
            "coordinates": coordinate,
            "scope": "global_requirement",
            "balloon_required": False,
            "requires_confirmation": True,
            "source_location_ids": list(
                requirement.get("source_location_ids", [])
            ),
            "source_type": "automatic",
            "status": "pending",
            "acceptance_source": None,
            "active": True,
        }
        items.append(item)
        return item

    def _set_technical_requirement_match(
        self,
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        technical_requirements: list[dict[str, Any]],
        command: SetTechnicalRequirementMatch,
        *,
        numbering_stale: bool,
    ) -> tuple[list[str], bool]:
        requirement = self._requirement(
            technical_requirements,
            command.requirement_id,
        )
        targets = [
            self._active_item(items, item_id)
            for item_id in command.matched_item_ids
        ]
        self._remove_requirement_projection(
            items,
            command.requirement_id,
        )

        target_ids: list[str] = [command.requirement_id]
        if command.outcome == "matched_items":
            ordered_ids = sorted(command.matched_item_ids)
            requirement.update(
                {
                    "match_outcome": "matched_items",
                    "matched_candidate_ids": ordered_ids,
                    "generated_candidate_id": None,
                    "review_required": False,
                    "review_status": "confirmed",
                }
            )
            for target in targets:
                self._add_requirement_ref(target, command.requirement_id)
                self._apply_requirement_suggestion(target, requirement)
            target_ids.extend(ordered_ids)
        elif command.outcome == "global_scope":
            item = self._global_requirement_item(items, requirement)
            generated_id = str(item["item_id"])
            requirement.update(
                {
                    "match_outcome": "global_scope",
                    "matched_candidate_ids": [],
                    "generated_candidate_id": generated_id,
                    "review_required": False,
                    "review_status": "confirmed",
                }
            )
            self._add_requirement_ref(item, command.requirement_id)
            self._apply_requirement_suggestion(item, requirement)
            target_ids.append(generated_id)
            numbering_stale = True
        else:
            requirement.update(
                {
                    "match_outcome": "unresolved",
                    "matched_candidate_ids": [],
                    "generated_candidate_id": None,
                    "review_required": False,
                    "review_status": "excluded",
                }
            )
            numbering_stale = True
        self._sync_requirement_coverage(
            coverage,
            technical_requirements,
            requirement,
        )
        return target_ids, numbering_stale

    @staticmethod
    def _mark_manual_acceptance(item: dict[str, Any]) -> None:
        try:
            validate_confidence_decision(item.get("confidence_decision"))
        except ConfidenceDecisionContractError:
            item.pop("confidence_decision", None)
        else:
            ReviewService._mark_manual_override(item)
            return
        item["status"] = "kept"
        item["requires_confirmation"] = False
        item["acceptance_source"] = "manual"

    @staticmethod
    def _mark_manual_override(item: dict[str, Any]) -> None:
        item["status"] = "kept"
        item["requires_confirmation"] = False
        item["acceptance_source"] = "manual_override"

    @staticmethod
    def _complete_manual_item(
        item: dict[str, Any],
        coverage: dict[str, Any],
        *,
        accepted: bool,
    ) -> None:
        ReviewService._mark_manual_acceptance(item)
        item["confirmation_accepted"] = accepted
        if not accepted:
            item["status"] = "excluded"
            item["active"] = False
        item_id = item["item_id"]
        for entry in ReviewService._coverage_entries(coverage):
            if entry.get("candidate_id") == item_id:
                entry["requires_confirmation"] = False
                entry["confirmation_accepted"] = accepted
        ReviewService._refresh_review_required_count(coverage)

    @staticmethod
    def _edit_item(item: dict[str, Any], fields: dict[str, Any]) -> None:
        validate_edit_fields(item, fields)
        if "coarse_type" in item:
            validated = dict(fields)
            if "coordinates" in validated:
                validated["coordinates"] = list(
                    _COORDINATES.validate_python(validated["coordinates"])
                )
            if "coarse_type" in validated:
                validated["coarse_type"] = _COARSE_TYPE.validate_python(
                    validated["coarse_type"]
                )
            if "raw_text" in validated and not isinstance(validated["raw_text"], str):
                raise ValueError("raw_text must be a string")
            if "requires_confirmation" in validated and not isinstance(
                validated["requires_confirmation"], bool
            ):
                raise ValueError("requires_confirmation must be a boolean")
        else:
            candidate_fields = {
                key: value
                for key, value in item.items()
                if key in Candidate.model_fields and key != "candidate_id"
            }
            candidate_fields.update(fields)
            validated_candidate = Candidate.model_validate(
                {"candidate_id": item["item_id"], **candidate_fields}
            ).model_dump(mode="json")
            validated = {key: validated_candidate[key] for key in fields}
        item.update(validated)
        item["source_type"] = "manual"

    @staticmethod
    def _ordered_source_union(items: list[dict[str, Any]]) -> list[str]:
        result: list[str] = []
        for item in items:
            for source_id in item.get("source_location_ids", []):
                if source_id not in result:
                    result.append(source_id)
        return result

    def _sip_source_page_indices(
        self,
        working: ReviewWorkingCopy,
    ) -> dict[str, int]:
        raw = self.session.get(AutomaticResult, working.raw_result_id)
        if raw is None:
            return {}
        storage = self.storage or LocalFileStorage(get_settings().storage_root)
        try:
            document = json.loads(storage.read_bytes(raw.inventory_ref))
            pages = document["pages"]
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(pages, list):
            return {}
        result: dict[str, int] = {}
        try:
            for page in pages:
                if not isinstance(page, dict):
                    return {}
                page_index = int(page["page_index"])
                if page_index < 0:
                    return {}
                for collection in ("observations", "visual_observations"):
                    values = page.get(collection, [])
                    if not isinstance(values, list):
                        return {}
                    for observation in values:
                        if not isinstance(observation, dict):
                            return {}
                        observation_id = observation.get("observation_id")
                        if isinstance(observation_id, str) and observation_id:
                            result[observation_id] = page_index
        except (KeyError, TypeError, ValueError):
            return {}
        return result

    @staticmethod
    def _clear_sip_detail_fields(item: dict[str, Any]) -> None:
        for field in (
            *SIP_DETAIL_FIELDS,
            *SIP_OPTIONAL_DETAIL_FIELDS,
            _SIP_DETAIL_CONFIRMED,
        ):
            item.pop(field, None)
        item.pop("sip_suggestion_provenance", None)
        item.pop("sip_mapping_exceptions", None)

    @staticmethod
    def _sip_fields_are_manual(item: dict[str, Any]) -> bool:
        if item.get(_SIP_DETAIL_CONFIRMED) is not True:
            return False
        provenance = item.get("sip_suggestion_provenance")
        return not (
            isinstance(provenance, dict)
            and SIP_MAPPING_RULE_VERSION in provenance.values()
        )

    @staticmethod
    def _clear_automatic_sip_fields(item: dict[str, Any]) -> None:
        provenance = item.get("sip_suggestion_provenance")
        if not isinstance(provenance, dict):
            return
        for field, source in list(provenance.items()):
            if source != SIP_MAPPING_RULE_VERSION:
                continue
            item.pop(field, None)
            provenance.pop(field, None)
        item.pop("sip_mapping_exceptions", None)
        item[_SIP_DETAIL_CONFIRMED] = False
        if not provenance:
            item.pop("sip_suggestion_provenance", None)

    @staticmethod
    def _sip_confirmation_blockers(
        items: list[dict[str, Any]],
        sip_metadata: dict[str, Any],
    ) -> list[str]:
        blockers: list[str] = []
        if set(sip_metadata) != set(SIP_METADATA_FIELDS) or any(
            not isinstance(sip_metadata.get(field), str)
            or not sip_metadata[field].strip()
            for field in SIP_METADATA_FIELDS
        ):
            blockers.append("sip_metadata_unconfirmed")
        active_items = [item for item in items if item.get("active", True)]
        if any(
            item.get(_SIP_DETAIL_CONFIRMED) is not True
            or any(
                (
                    not isinstance(item.get(field), int)
                    or isinstance(item.get(field), bool)
                    or item[field] < 1
                )
                if field == "source_page"
                else (
                    not isinstance(item.get(field), str)
                    or not item[field].strip()
                )
                for field in SIP_DETAIL_FIELDS
            )
            for item in active_items
        ):
            blockers.append("sip_detail_fields_unconfirmed")
        return blockers

    @staticmethod
    def _resolve_confirmation(
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        item_id: str,
        accepted: bool,
    ) -> None:
        item = ReviewService._active_item(items, item_id)
        ReviewService._complete_manual_item(
            item,
            coverage,
            accepted=accepted,
        )

    @staticmethod
    def _pending_source_entry(
        coverage: dict[str, Any],
        observation_id: str,
    ) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        for entry in ReviewService._coverage_entries(coverage):
            if entry.get("observation_id") == observation_id:
                matches.append(entry)
        if (
            len(matches) != 1
            or matches[0].get("requires_confirmation") is not True
            or matches[0].get("candidate_id") is not None
        ):
            raise ReviewNotFound(
                f"source review target {observation_id} was not found"
            )
        return matches[0]

    @staticmethod
    def _coverage_entries(
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        entries = coverage.get("entries", [])
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) for entry in entries
        ):
            raise ReviewNotFound("review coverage entries are malformed")
        return entries

    @staticmethod
    def _refresh_review_required_count(coverage: dict[str, Any]) -> None:
        coverage["review_required_count"] = sum(
            entry.get("requires_confirmation") is True
            for entry in ReviewService._coverage_entries(coverage)
        )

    @staticmethod
    def _operator_id(operator_id: str) -> str:
        if not operator_id.strip():
            raise ValueError("operator_id must not be blank")
        return operator_id
