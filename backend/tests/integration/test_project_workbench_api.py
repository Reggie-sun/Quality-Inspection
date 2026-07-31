from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.candidates.models import AutomaticResult
from app.db import engine
from app.exports.models import ExportJob
from app.exports.service import ExportService
from app.main import app
from app.projects.router import _project_items
from app.projects.router import get_session as get_project_session
from app.projects.router import get_storage
from app.review.router import _working_copy as _review_working_copy
from app.review.models import ReviewedResult
from app.review.service import ReviewService
from app.storage.models import StoredFile


_BALLOON_TEST_MODULE = "_qi_test_balloon_service"
_balloon_test_spec = importlib.util.spec_from_file_location(
    _BALLOON_TEST_MODULE,
    Path(__file__).with_name("test_balloon_service.py"),
)
assert _balloon_test_spec is not None and _balloon_test_spec.loader is not None
_balloon_test_module = importlib.util.module_from_spec(_balloon_test_spec)
sys.modules[_BALLOON_TEST_MODULE] = _balloon_test_module
_balloon_test_spec.loader.exec_module(_balloon_test_module)
make_balloon_context = _balloon_test_module.make_balloon_context


def _valid_source_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_text((20, 20), "Task 4 workbench recovery")
    content = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    document.close()
    return content


def _title_observation(
    observation_id: str,
    text: str,
    bbox_pdf: list[float],
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "source_type": "native",
        "observation_level": "line",
        "raw_text": text,
        "normalized_text": text,
        "page_index": 0,
        "bbox_pdf": bbox_pdf,
        "bbox_normalized": [0.0, 0.0, 0.0, 0.0],
        "direction": [1.0, 0.0],
        "direction_angle_degrees": 0.0,
        "confidence": None,
    }


def test_project_workbench_delivers_real_pdf_without_internal_references(
    tmp_path: Path,
) -> None:
    """P0-UI-005/P0-UI-008 bootstrap one aggregate and controlled PDF bytes."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=True)
    generated = context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    expected_pdf = context.storage.read_bytes(
        f"asset://projects/{context.working_copy.project_id}/source.pdf"
    )

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        client = TestClient(app)
        base = f"/api/v1/projects/{context.working_copy.project_id}"
        export_count_before = session.scalar(
            select(func.count()).select_from(ExportJob)
        )
        reviewed_count_before = session.scalar(
            select(func.count()).select_from(ReviewedResult)
        )

        response = client.get(f"{base}/workbench")

        assert response.status_code == 200
        payload = response.json()
        assert payload["project"] == {
            "id": str(context.working_copy.project_id),
            "state": "editing",
            "version": 1,
        }
        assert payload["working_copy"]["id"] == str(context.working_copy.id)
        assert payload["working_copy"]["version"] == context.working_copy.version
        assert payload["working_copy"]["manual_review_count"] == 0
        assert payload["source_pdf_url"] == f"{base}/source-pdf"
        assert payload["pages"] == [
            {
                "page_index": 0,
                "width": 200.0,
                "height": 200.0,
                "pdf_to_render_matrix": [1, 0, 0, 1, 0, 0],
                "render_to_pdf_matrix": [1, 0, 0, 1, 0, 0],
            }
        ]
        assert payload["candidates"][0]["item_id"] == "i1"
        assert payload["sources"][0]["item_ids"] == ["i1"]
        assert payload["balloons"][0]["inspection_item_id"] == "i1"
        assert {value["id"] for value in payload["balloons"]} == {
            str(value.id) for value in generated
        }
        assert payload["reviewed_result_id"] is None
        assert payload["latest_export"] is None
        assert session.scalar(select(func.count()).select_from(ExportJob)) == (
            export_count_before
        )
        assert session.scalar(select(func.count()).select_from(ReviewedResult)) == (
            reviewed_count_before
        )
        serialized = response.text
        assert "resource_ref" not in serialized
        assert "asset://" not in serialized
        assert str(tmp_path) not in serialized

        source = client.get(payload["source_pdf_url"])
        assert source.status_code == 200
        assert source.content == expected_pdf
        assert source.headers["content-type"] == "application/pdf"
        assert "content-disposition" not in source.headers
        assert "asset://" not in str(source.headers)

        missing = client.get(f"/api/v1/projects/00000000-0000-0000-0000-000000000000/workbench")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "project_not_found"
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_project_workbench_projects_title_block_suggestions_without_confirming(
    tmp_path: Path,
) -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=False)
    raw = session.get(AutomaticResult, context.working_copy.raw_result_id)
    assert raw is not None
    inventory = json.loads(context.storage.read_bytes(raw.inventory_ref))
    page = inventory["pages"][0]
    page["width"] = 1190.550048828125
    page["height"] = 841.8900146484375
    page["observations"] = [
        _title_observation(
            "material-code-label",
            "物料编码",
            [1037.62, 806.98, 1071.06, 821.72],
        ),
        _title_observation(
            "material-code-value",
            "12320096476",
            [1098.47, 807.02, 1152.38, 821.77],
        ),
        _title_observation(
            "drawing-number-label",
            "图样代号",
            [1037.62, 781.46, 1071.07, 796.21],
        ),
        _title_observation(
            "drawing-number-value",
            "ZHZS25032501-04",
            [1088.29, 781.55, 1162.57, 796.3],
        ),
        _title_observation(
            "revision-label",
            "版本号",
            [818.01, 730.45, 843.1, 745.2],
        ),
        _title_observation(
            "revision-value",
            "A/0",
            [821.55, 710.48, 839.54, 725.22],
        ),
        _title_observation(
            "material-name-value",
            "横行滑板",
            [1088.47, 739.28, 1121.92, 754.02],
        ),
    ]
    inventory_bytes = json.dumps(inventory).encode("utf-8")
    context.storage.write_verified(
        raw.inventory_ref.removeprefix("asset://"),
        inventory_bytes,
        hashlib.sha256(inventory_bytes).hexdigest(),
    )
    context.working_copy.sip_metadata = {}
    session.commit()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        response = TestClient(app).get(
            f"/api/v1/projects/{context.working_copy.project_id}/workbench"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["working_copy"]["sip_metadata"] == {}
        assert payload["sip_metadata_suggestions"][0] == {
            "field": "material_code",
            "value": "12320096476",
            "observation_id": "material-code-value",
            "label_observation_id": "material-code-label",
            "page_index": 0,
            "bbox_pdf": [1098.47, 807.02, 1152.38, 821.77],
            "rule_version": "welli-title-metadata/1",
            "evidence_codes": [
                "bottom_right_title_anchor",
                "native_line",
                "same_row_right_of_label",
                "unique_candidate",
            ],
        }
        assert {
            suggestion["field"]: suggestion["value"]
            for suggestion in payload["sip_metadata_suggestions"]
        } == {
            "material_code": "12320096476",
            "material_name": "横行滑板",
            "drawing_number": "ZHZS25032501-04",
            "revision": "A/0",
        }
        serialized = response.text
        assert "resource_ref" not in serialized
        assert "asset://" not in serialized
        assert str(tmp_path) not in serialized
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_project_workbench_projects_source_only_coverage_for_review(
    tmp_path: Path,
) -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=False)
    raw = session.get(AutomaticResult, context.working_copy.raw_result_id)
    assert raw is not None
    inventory = json.loads(context.storage.read_bytes(raw.inventory_ref))
    inventory["pages"][0]["observations"].append(
        {
            "observation_id": "source-only",
            "source_type": "native_text",
            "observation_level": "line",
            "raw_text": "技术要求：去除毛刺",
            "normalized_text": "技术要求:去除毛刺",
            "page_index": 0,
            "bbox_pdf": [60.0, 70.0, 150.0, 84.0],
            "bbox_normalized": [0.3, 0.35, 0.75, 0.42],
            "direction": [1.0, 0.0],
            "direction_angle_degrees": 0.0,
            "confidence": None,
        }
    )
    inventory["pages"][0]["observations"].append(
        {
            "observation_id": "source-resolved",
            "source_type": "native_text",
            "observation_level": "line",
            "raw_text": "仅供参考",
            "normalized_text": "仅供参考",
            "page_index": 0,
            "bbox_pdf": [20.0, 30.0, 50.0, 44.0],
            "bbox_normalized": [0.1, 0.15, 0.25, 0.22],
            "direction": [1.0, 0.0],
            "direction_angle_degrees": 0.0,
            "confidence": None,
        }
    )
    inventory["pages"][0]["visual_observations"] = [
        {
            "observation_id": "visual-observation-id",
            "source_type": "visual",
            "observation_level": "annotation_context",
            "page_index": 0,
            "bbox_pdf": [60.0, 70.0, 100.0, 90.0],
            "bbox_normalized": [0.3, 0.35, 0.5, 0.45],
            "proposal_kind": "text_adjacent_vector_context",
            "geometry_sha256": "a" * 64,
            "associated_text_observation_ids": ["source-only"],
        },
        {
            "observation_id": "visual-revision-id",
            "source_type": "visual",
            "observation_level": "annotation_context",
            "page_index": 0,
            "bbox_pdf": [160.0, 70.0, 190.0, 100.0],
            "bbox_normalized": [0.8, 0.35, 0.95, 0.5],
            "proposal_kind": "text_adjacent_vector_context",
            "geometry_sha256": "b" * 64,
            "associated_text_observation_ids": [],
        },
    ]
    inventory_bytes = json.dumps(inventory).encode("utf-8")
    context.storage.write_verified(
        raw.inventory_ref.removeprefix("asset://"),
        inventory_bytes,
        hashlib.sha256(inventory_bytes).hexdigest(),
    )
    coverage = copy.deepcopy(context.working_copy.coverage)
    coverage["entries"] = [
        {
            "observation_id": "source-only",
            "source_location_id": "source-only",
            "candidate_id": None,
            "disposition": "ambiguous",
            "coordinates": [60.0, 70.0, 150.0, 84.0],
            "requires_confirmation": True,
        },
        {
            "observation_id": "source-resolved",
            "source_location_id": "source-resolved",
            "candidate_id": None,
            "disposition": "reference_context",
            "coordinates": [20.0, 30.0, 50.0, 44.0],
            "requires_confirmation": False,
        },
        {
            "observation_id": "visual-observation-id",
            "source_location_id": "visual-observation-id",
            "candidate_id": None,
            "disposition": "ambiguous",
            "coordinates": [60.0, 70.0, 100.0, 90.0],
            "requires_confirmation": True,
            "symbol_kinds": [],
            "rejection_code": "visual_no_detection",
        },
        {
            "observation_id": "visual-revision-id",
            "source_location_id": "visual-revision-id",
            "candidate_id": None,
            "disposition": "non_inspection",
            "coordinates": [160.0, 70.0, 190.0, 100.0],
            "requires_confirmation": True,
            "symbol_kinds": ["revision_marker"],
        },
    ]
    coverage["review_required_count"] = 3
    context.working_copy.coverage = coverage
    session.commit()

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/projects/{context.working_copy.project_id}/workbench"
        )

        assert response.status_code == 200
        assert response.json()["working_copy"]["manual_review_count"] == 3
        assert (
            _review_working_copy(context.working_copy)["manual_review_count"]
            == 3
        )
        source = next(
            item
            for item in response.json()["sources"]
            if item["id"] == "source-only"
        )
        assert source == {
            "id": "source-only",
            "item_ids": [],
            "page_index": 0,
            "bbox_pdf": [60.0, 70.0, 150.0, 84.0],
            "raw_text": "技术要求：去除毛刺",
            "source_type": "text",
        }
        visual_source = next(
            item
            for item in response.json()["sources"]
            if item["id"] == "visual-observation-id"
        )
        assert visual_source == {
            "id": "visual-observation-id",
            "item_ids": [],
            "page_index": 0,
            "bbox_pdf": [60.0, 70.0, 100.0, 90.0],
            "raw_text": "图形符号待确认",
            "source_type": "visual",
        }
        visual_revision = next(
            item
            for item in response.json()["sources"]
            if item["id"] == "visual-revision-id"
        )
        assert visual_revision == {
            "id": "visual-revision-id",
            "item_ids": [],
            "page_index": 0,
            "bbox_pdf": [160.0, 70.0, 190.0, 100.0],
            "raw_text": "图形符号待确认",
            "source_type": "visual",
        }
        projected_revision = next(
            entry
            for entry in response.json()["working_copy"]["coverage"]["entries"]
            if entry["observation_id"] == "visual-revision-id"
        )
        assert projected_revision["disposition"] == "non_inspection"
        assert projected_revision["symbol_kinds"] == ["revision_marker"]
        serialized = json.dumps(response.json(), ensure_ascii=False)
        assert "advisor_review" not in serialized
        assert "geometry_sha256" not in serialized
        assert "associated_text_observation_ids" not in serialized
        assert "text_adjacent_vector_context" not in serialized
        assert all(
            item["id"] != "source-resolved"
            for item in response.json()["sources"]
        )
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()


def test_project_candidate_projection_exposes_backend_confidence_status() -> None:
    items = [
        {
            "item_id": "high",
            "active": True,
            "page_index": 0,
            "coordinates": [1, 2, 3, 4],
            "source_location_ids": ["source-high"],
            "status": "auto_accepted",
            "confidence_decision": {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/1",
                "evidence_codes": ["typed_schema_complete"],
            },
        },
        {
            "item_id": "legacy",
            "active": True,
            "page_index": 0,
            "coordinates": [5, 6, 7, 8],
            "source_location_ids": ["source-legacy"],
            "status": "pending",
        },
    ]
    observations = {
        "source-high": {
            "page_index": 0,
            "bbox_pdf": [1, 2, 3, 4],
            "raw_text": "M6",
            "source_type": "text",
        },
        "source-legacy": {
            "page_index": 0,
            "bbox_pdf": [5, 6, 7, 8],
            "raw_text": "M8",
            "source_type": "text",
        },
    }

    candidates, _ = _project_items(items, {"entries": []}, observations)

    assert candidates == [
        {
            "id": "candidate-high",
            "item_id": "high",
            "page_index": 0,
            "bbox_pdf": [1, 2, 3, 4],
            "confidence_band": "high",
            "review_disposition": "auto_accepted",
            "status": "auto_accepted",
        },
        {
            "id": "candidate-legacy",
            "item_id": "legacy",
            "page_index": 0,
            "bbox_pdf": [5, 6, 7, 8],
            "confidence_band": None,
            "review_disposition": None,
            "status": "pending",
        },
    ]


def test_project_projection_fails_closed_for_historical_malformed_decision() -> None:
    items = [
        {
            "item_id": "malformed",
            "active": True,
            "page_index": 0,
            "coordinates": [1, 2, 3, 4],
            "source_location_ids": ["source-malformed"],
            "status": "pending",
            "confidence_decision": {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/999",
                "evidence_codes": [],
            },
        }
    ]

    candidates, _ = _project_items(
        items,
        {"entries": []},
        {
            "source-malformed": {
                "page_index": 0,
                "bbox_pdf": [1, 2, 3, 4],
                "raw_text": "M6",
                "source_type": "text",
            }
        },
    )

    assert candidates[0]["confidence_band"] is None
    assert candidates[0]["review_disposition"] is None
    assert candidates[0]["status"] == "pending"


@pytest.mark.parametrize(
    ("schema_version", "top_level_decision"),
    [
        ("automatic-result/1", None),
        (
            "automatic-result/2",
            {
                "band": "high",
                "review_disposition": "auto_accepted",
                "policy_version": "candidate-confidence/1",
                "evidence_codes": ["typed_schema_complete"],
                "extra": True,
            },
        ),
    ],
)
def test_project_projection_does_not_expose_payload_forged_confidence(
    schema_version: str,
    top_level_decision: object,
) -> None:
    forged = {
        "band": "high",
        "review_disposition": "auto_accepted",
        "policy_version": "candidate-confidence/1",
        "evidence_codes": ["typed_schema_complete"],
    }
    candidate = {
        "candidate_id": "forged",
        "payload": {
            "candidate_id": "forged",
            "item_type": "thread",
            "raw_text": "M6",
            "normalized_text": "M6",
            "coordinates": [1, 2, 3, 4],
            "scope": "local_feature",
            "balloon_required": True,
            "requires_confirmation": False,
            "confidence_decision": forged,
        },
        "source_location_ids": ["source-forged"],
    }
    if top_level_decision is not None:
        candidate["confidence_decision"] = top_level_decision
    item = ReviewService._current_item(candidate, schema_version)

    projected, _ = _project_items(
        [item],
        {"entries": []},
        {
            "source-forged": {
                "page_index": 0,
                "bbox_pdf": [1, 2, 3, 4],
                "raw_text": "M6",
                "source_type": "text",
            }
        },
    )

    assert projected[0]["status"] == "pending"
    assert projected[0]["confidence_band"] is None
    assert projected[0]["review_disposition"] is None


def test_project_workbench_recovers_reviewed_result_and_latest_atomic_export(
    tmp_path: Path,
) -> None:
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    context = make_balloon_context(session, tmp_path, frozen=True)
    raw = session.get(AutomaticResult, context.working_copy.raw_result_id)
    assert raw is not None
    source = session.get(StoredFile, raw.source_file_id)
    assert source is not None
    source_bytes = _valid_source_pdf()
    stored = context.storage.write_verified(
        source.resource_ref.removeprefix("asset://"),
        source_bytes,
        hashlib.sha256(source_bytes).hexdigest(),
    )
    source.sha256 = stored.sha256
    source.size_bytes = stored.size_bytes
    session.commit()
    context.balloon_service.generate_formal(
        context.working_copy.project_id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    reviewed = context.review_service.confirm(
        context.working_copy.id,
        expected_version=context.working_copy.version,
        operator_id="quality-1",
    )
    exported = ExportService(session, storage=context.storage).create(reviewed.id)
    assert exported.status == "success"

    def override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_project_session] = override_session
    app.dependency_overrides[get_storage] = lambda: context.storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/projects/{context.working_copy.project_id}/workbench"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["reviewed_result_id"] == str(reviewed.id)
        latest = payload["latest_export"]
        assert {
            key: latest[key]
            for key in (
                "id",
                "project_id",
                "reviewed_result_id",
                "status",
                "error_id",
            )
        } == {
            "id": str(exported.id),
            "project_id": str(reviewed.project_id),
            "reviewed_result_id": str(reviewed.id),
            "status": "success",
            "error_id": None,
        }
        assert [artifact["kind"] for artifact in latest["artifacts"]] == [
            "ballooned_pdf",
            "sip_excel",
            "manifest",
        ]
        assert len(latest["artifacts"]) == 3
        for artifact in latest["artifacts"]:
            assert set(artifact) == {
                "kind",
                "sha256",
                "size_bytes",
                "reviewed_result_id",
                "downloadable",
            }
            assert artifact["sha256"]
            assert artifact["size_bytes"] > 0
            assert artifact["reviewed_result_id"] == str(reviewed.id)
            assert artifact["downloadable"] is True
        assert session.scalar(
            select(func.count()).select_from(ExportJob)
        ) == 1
        assert session.get(ReviewedResult, reviewed.id) is reviewed
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer_transaction.rollback()
        connection.close()
