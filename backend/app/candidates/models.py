from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AutomaticResult(Base):
    __tablename__ = "automatic_results"
    __table_args__ = (
        UniqueConstraint(
            "logical_job_id",
            name="uq_automatic_results_logical_job_id",
        ),
        CheckConstraint(
            "completeness IN ('complete', 'partial_review_required')",
            name="ck_automatic_results_completeness",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stored_files.id"),
        nullable=False,
    )
    logical_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("logical_jobs.id"),
        nullable=False,
    )
    inventory_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    technical_requirements: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    provider_call_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    completeness: Mapped[str] = mapped_column(
        String(32),
        default="complete",
        server_default="complete",
        nullable=False,
    )
    recognition_mode: Mapped[str] = mapped_column(
        String(40),
        default="legacy_high_recall",
        server_default="legacy_high_recall",
        nullable=False,
    )
    router_version: Mapped[str] = mapped_column(
        String(64),
        default="legacy",
        server_default="legacy",
        nullable=False,
    )
    recognition_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    recognition_evidence_ref: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SymbolRoutingDecisionRecord(Base):
    __tablename__ = "symbol_routing_decisions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "visual_observation_id",
            name="uq_symbol_routing_decision_observation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    visual_observation_id: Mapped[str] = mapped_column(
        String(256), nullable=False
    )
    escalation_group_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    escalation_group_member_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    local_resolution_ref: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    router_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    local_resolution_reason_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    escalation_reason_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    block_reason_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VisualSymbolCacheEntryRecord(Base):
    __tablename__ = "visual_symbol_cache_entries"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "cache_key",
            name="uq_visual_symbol_cache_project_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_schema_version: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    producer_request_id: Mapped[str] = mapped_column(
        String(256), nullable=False
    )
    producer_call_record_ref: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    producer_provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    provenance_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SymbolEscalationAttemptEventRecord(Base):
    __tablename__ = "symbol_escalation_attempt_events"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "escalation_group_id",
            "attempt_index",
            "event_code",
            name="uq_symbol_escalation_attempt_event",
        ),
        UniqueConstraint(
            "project_id",
            "event_sha256",
            name="uq_symbol_escalation_attempt_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    escalation_group_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    routing_decision_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    event_code: Mapped[str] = mapped_column(String(48), nullable=False)
    cache_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("visual_symbol_cache_entries.id"),
        nullable=True,
    )
    provider_request_id: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SymbolEscalationOutcomeRecord(Base):
    __tablename__ = "symbol_escalation_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "escalation_group_id",
            name="uq_symbol_escalation_outcome_group",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    escalation_group_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    routing_decision_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_code: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_outcomes: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False
    )
    attempt_event_sha256s: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False
    )
    terminal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
