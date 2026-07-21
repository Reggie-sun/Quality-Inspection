from __future__ import annotations

import copy
import uuid
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.candidates.complex_fallback import CoarseType
from app.candidates.models import AutomaticResult
from app.candidates.schemas import Candidate
from app.projects.models import Project
from app.projects.state import ProjectState, transition
from app.review.locks import require_active_lock
from app.review.models import ReviewWorkingCopy
from app.review.schemas import (
    Add,
    Edit,
    Exclude,
    Keep,
    Merge,
    ResolveConfirmation,
    ReviewCommand,
    SetBalloonRequired,
    Split,
    parse_review_command,
    validate_edit_fields,
)


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


_COORDINATES = TypeAdapter(tuple[float, float, float, float])
_COARSE_TYPE = TypeAdapter(CoarseType)


class ReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

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

        working = ReviewWorkingCopy(
            project_id=raw_result.project_id,
            raw_result_id=raw_result.id,
            version=1,
            items=[self._current_item(candidate) for candidate in raw_result.candidates],
            coverage=copy.deepcopy(raw_result.coverage),
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
        target_ids, numbering_stale = self._apply_command(
            items,
            coverage,
            parsed,
            numbering_stale=working.numbering_stale,
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

        blockers = self.freeze_blockers(working.items, working.coverage)
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
        if unresolved_item or unresolved_coverage:
            blockers.append("unresolved_confirmation")
        if any(
            item.get("active", True) and item.get("balloon_required") is None
            for item in items
        ):
            blockers.append("balloon_required_unconfirmed")
        return blockers

    @staticmethod
    def reviewed_result_for(_: uuid.UUID) -> None:
        return None

    @staticmethod
    def _current_item(candidate: dict[str, Any]) -> dict[str, Any]:
        item_id = str(candidate["candidate_id"])
        payload = copy.deepcopy(candidate["payload"])
        payload.pop("candidate_id", None)
        return {
            "item_id": item_id,
            **payload,
            "source_location_ids": list(candidate.get("source_location_ids", [])),
            "source_type": "automatic",
            "status": "pending",
            "active": True,
        }

    def _apply_command(
        self,
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        command: ReviewCommand,
        *,
        numbering_stale: bool,
    ) -> tuple[list[str], bool]:
        if isinstance(command, Keep):
            item = self._active_item(items, command.item_id)
            item["status"] = "kept"
            return [command.item_id], numbering_stale
        if isinstance(command, Exclude):
            item = self._active_item(items, command.item_id)
            item["status"] = "excluded"
            item["active"] = False
            return [command.item_id], numbering_stale
        if isinstance(command, Edit):
            item = self._active_item(items, command.item_id)
            self._edit_item(item, command.fields)
            return [command.item_id], numbering_stale
        if isinstance(command, Add):
            item_id = str(uuid.uuid4())
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
                    "source_location_ids": [],
                    "source_type": "manual",
                    "status": "pending",
                    "active": True,
                }
            )
            return [item_id], numbering_stale
        if isinstance(command, Merge):
            if len(set(command.item_ids)) != len(command.item_ids):
                raise ValueError("merge item IDs must be distinct")
            source_items = [self._active_item(items, item_id) for item_id in command.item_ids]
            item_type = source_items[0].get("item_type")
            if item_type is None or any(
                source.get("item_type") != item_type for source in source_items
            ):
                raise ValueError("merge requires the same simple item type")
            merged_id = str(uuid.uuid4())
            merged = copy.deepcopy(source_items[0])
            merged.update(
                {
                    "item_id": merged_id,
                    "raw_text": command.raw_text,
                    "normalized_text": command.raw_text,
                    "quantity": None,
                    "source_location_ids": self._ordered_source_union(source_items),
                    "source_type": "manual",
                    "status": "pending",
                    "active": True,
                    "merged_from_item_ids": list(command.item_ids),
                }
            )
            for source in source_items:
                source["status"] = "superseded"
                source["active"] = False
            items.append(merged)
            return [*command.item_ids, merged_id], numbering_stale
        if isinstance(command, Split):
            source = self._active_item(items, command.item_id)
            if "item_type" not in source:
                raise ValueError("split is limited to simple items")
            source["status"] = "superseded"
            source["active"] = False
            split_ids: list[str] = []
            for part in command.parts:
                split_id = str(uuid.uuid4())
                split_ids.append(split_id)
                split_item = copy.deepcopy(source)
                split_item.update(
                    {
                        "item_id": split_id,
                        "raw_text": part.raw_text,
                        "normalized_text": part.raw_text,
                        "quantity": None,
                        "source_type": "manual",
                        "status": "pending",
                        "active": True,
                        "split_from_item_id": command.item_id,
                    }
                )
                items.append(split_item)
            return [command.item_id, *split_ids], numbering_stale
        if isinstance(command, ResolveConfirmation):
            self._resolve_confirmation(
                items,
                coverage,
                command.item_id,
                command.accepted,
            )
            return [command.item_id], numbering_stale
        if isinstance(command, SetBalloonRequired):
            item = self._active_item(items, command.item_id)
            item["balloon_required"] = command.balloon_required
            return [command.item_id], True
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

    @staticmethod
    def _resolve_confirmation(
        items: list[dict[str, Any]],
        coverage: dict[str, Any],
        item_id: str,
        accepted: bool,
    ) -> None:
        resolved = False
        for item in items:
            if item["item_id"] == item_id and item.get("active", True):
                item["requires_confirmation"] = False
                item["confirmation_accepted"] = accepted
                resolved = True
        for entry in coverage.get("entries", []):
            if item_id in {entry.get("candidate_id"), entry.get("observation_id")}:
                entry["requires_confirmation"] = False
                entry["confirmation_accepted"] = accepted
                resolved = True
        if not resolved:
            raise ReviewNotFound(f"confirmation target {item_id} was not found")
        coverage["review_required_count"] = sum(
            bool(entry.get("requires_confirmation"))
            for entry in coverage.get("entries", [])
        )

    @staticmethod
    def _operator_id(operator_id: str) -> str:
        if not operator_id.strip():
            raise ValueError("operator_id must not be blank")
        return operator_id
