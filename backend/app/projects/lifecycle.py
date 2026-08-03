from __future__ import annotations

import uuid
from collections.abc import Callable
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.symbol_routing import validate_frozen_symbol_routing_identity
from app.projects.models import Project, ProjectLifecycleStatus
from app.projects.source import ProjectSourceUnavailable, project_source_file
from app.projects.state import ProjectState
from app.review.models import ReviewLock, ReviewWorkingCopy


ProjectDispatcher = Callable[[str, str, str], object]


class ProjectAccess(StrEnum):
    ACTIVE = "active"
    PROCESSING_READ = "processing_read"
    STATUS_READ = "status_read"


class ProjectLifecycleNotFound(LookupError):
    pass


class ProjectReprocessInProgress(RuntimeError):
    pass


class ProjectLifecycleLocked(RuntimeError):
    pass


class ProjectPromotionNotReady(RuntimeError):
    pass


class ProjectLifecycleDispatchFailed(RuntimeError):
    def __init__(self, project_id: uuid.UUID) -> None:
        super().__init__("project reprocessing dispatch failed")
        self.project_id = project_id


class ProjectLifecycleService:
    def __init__(
        self,
        session: Session,
        *,
        dispatch: ProjectDispatcher | None = None,
    ) -> None:
        self.session = session
        self.dispatch = dispatch

    def start_reprocess(
        self,
        project_id: uuid.UUID,
        *,
        recognition_mode: str,
        recognition_router_version: str,
    ) -> Project:
        mode, router_version = validate_frozen_symbol_routing_identity(
            recognition_mode,
            recognition_router_version,
        )
        predecessor = self.session.scalar(
            select(Project)
            .where(
                Project.id == project_id,
                Project.lifecycle_status == ProjectLifecycleStatus.ACTIVE,
            )
            .with_for_update()
        )
        if predecessor is None or predecessor.source_filename is None:
            raise ProjectLifecycleNotFound("project was not found")
        if self.dispatch is None:
            raise RuntimeError("project lifecycle dispatcher is unavailable")

        pending = self.session.scalar(
            select(Project).where(
                Project.predecessor_project_id == predecessor.id,
                Project.lifecycle_status == ProjectLifecycleStatus.REPROCESSING,
            )
        )
        if pending is not None:
            raise ProjectReprocessInProgress("project reprocessing is in progress")
        source = project_source_file(self.session, predecessor.id)
        if source.mime_type != "application/pdf":
            raise ProjectSourceUnavailable("project source PDF is unavailable")

        successor = Project(
            id=uuid.uuid4(),
            state=ProjectState.PROCESSING,
            recognition_mode=mode,
            recognition_router_version=router_version,
            source_filename=predecessor.source_filename,
            lifecycle_status=ProjectLifecycleStatus.REPROCESSING,
            predecessor_project_id=predecessor.id,
        )
        self.session.add(successor)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        try:
            self.dispatch(
                str(successor.id),
                source.resource_ref,
                f"product-process:{successor.id}",
            )
        except Exception as error:
            self.mark_reprocess_failed(successor.id)
            raise ProjectLifecycleDispatchFailed(successor.id) from error
        return successor

    def mark_reprocess_failed(self, project_id: uuid.UUID) -> None:
        project = self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if project is None:
            return
        if project.lifecycle_status == ProjectLifecycleStatus.REPROCESSING:
            project.lifecycle_status = ProjectLifecycleStatus.REPROCESS_FAILED
            self.session.commit()

    def promote_reprocessed_project(self, project_id: uuid.UUID) -> None:
        observed = self.session.get(Project, project_id, populate_existing=True)
        if observed is None or observed.predecessor_project_id is None:
            return
        predecessor_id = observed.predecessor_project_id
        predecessor = self.session.scalar(
            select(Project)
            .where(Project.id == predecessor_id)
            .with_for_update()
        )
        successor = self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if predecessor is None or successor is None:
            raise ProjectLifecycleNotFound("project was not found")
        if (
            predecessor.lifecycle_status == ProjectLifecycleStatus.SUPERSEDED
            and successor.lifecycle_status == ProjectLifecycleStatus.ACTIVE
        ):
            self.session.commit()
            return
        if (
            predecessor.lifecycle_status != ProjectLifecycleStatus.ACTIVE
            or successor.lifecycle_status != ProjectLifecycleStatus.REPROCESSING
        ):
            raise ProjectPromotionNotReady("project lifecycle cannot be promoted")
        working_copy = self.session.scalar(
            select(ReviewWorkingCopy).where(
                ReviewWorkingCopy.project_id == successor.id
            )
        )
        if working_copy is None:
            raise ProjectPromotionNotReady("successor working copy is unavailable")

        predecessor.lifecycle_status = ProjectLifecycleStatus.SUPERSEDED
        successor.lifecycle_status = ProjectLifecycleStatus.ACTIVE
        self.session.commit()

    def delete_project(self, project_id: uuid.UUID) -> None:
        project = self.session.scalar(
            select(Project)
            .where(
                Project.id == project_id,
                Project.lifecycle_status == ProjectLifecycleStatus.ACTIVE,
            )
            .with_for_update()
        )
        if project is None:
            raise ProjectLifecycleNotFound("project was not found")
        successor = self.session.scalar(
            select(Project)
            .where(
                Project.predecessor_project_id == project.id,
                Project.lifecycle_status == ProjectLifecycleStatus.REPROCESSING,
            )
            .with_for_update()
        )
        if successor is not None:
            raise ProjectReprocessInProgress("project reprocessing is in progress")

        now = self.session.scalar(select(func.now()))
        if now is None:
            raise RuntimeError("PostgreSQL database clock was unavailable")
        lock = self.session.scalar(
            select(ReviewLock)
            .where(ReviewLock.project_id == project.id)
            .with_for_update()
        )
        if lock is not None and lock.expires_at > now:
            raise ProjectLifecycleLocked("project has an active editor")
        if lock is not None:
            self.session.delete(lock)

        project.lifecycle_status = ProjectLifecycleStatus.DELETED
        project.deleted_at = now
        self.session.commit()

    def require_access(
        self,
        project_id: uuid.UUID,
        access: ProjectAccess,
    ) -> Project:
        project = self.session.get(Project, project_id, populate_existing=True)
        if project is None:
            raise ProjectLifecycleNotFound("project was not found")
        status = ProjectLifecycleStatus(project.lifecycle_status)
        allowed = (
            status in {
                ProjectLifecycleStatus.ACTIVE,
                ProjectLifecycleStatus.UNLISTED,
            }
            or (
                status == ProjectLifecycleStatus.REPROCESSING
                and access in {
                    ProjectAccess.PROCESSING_READ,
                    ProjectAccess.STATUS_READ,
                }
            )
            or (
                status == ProjectLifecycleStatus.REPROCESS_FAILED
                and access == ProjectAccess.STATUS_READ
            )
        )
        if not allowed:
            raise ProjectLifecycleNotFound("project was not found")
        return project
