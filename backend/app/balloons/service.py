from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.operations import OperationRecord
from app.balloons.models import Balloon
from app.balloons.numbering import (
    NumberableItem,
    assign_formal_numbers,
    assign_suggested_numbers,
)
from app.balloons.placement import (
    BALLOON_RADIUS_PDF,
    OccupiedBalloon,
    PlacementItem,
    PlacementResult,
    PlacementScene,
    evaluate_placement,
    glyph_bbox,
    place_balloons,
)
from app.balloons.schemas import BBox, PdfPoint
from app.balloons.validator import validate_balloons
from app.candidates.models import AutomaticResult
from app.config import get_settings
from app.projects.models import Project
from app.projects.state import ProjectState
from app.review.locks import require_active_lock
from app.review.models import ReviewedResult, ReviewWorkingCopy
from app.storage.local import LocalFileStorage


PROTECTED_TEXT_TOKENS = (
    "approved",
    "checked",
    "signature",
    "sign-off",
    "审核",
    "批准",
    "签字",
    "校对",
)
REGISTERED_ADMINISTRATION_STRIP_START = 0.79


class BalloonNotFound(LookupError):
    pass


class ItemSetNotFrozen(RuntimeError):
    pass


class BalloonVersionConflict(RuntimeError):
    pass


class BalloonSourceUnavailable(RuntimeError):
    pass


class BalloonOrderConflict(RuntimeError):
    pass


class BalloonReviewFinalized(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceGeometry:
    source_location_id: str
    page_index: int
    anchor_bbox: BBox
    direction: PdfPoint
    page_size: PdfPoint
    forbidden: tuple[BBox, ...]


@dataclass(frozen=True)
class InventoryIndex:
    page_sizes: dict[int, PdfPoint]
    source_geometries: dict[str, SourceGeometry]
    source_text_boxes: dict[int, tuple[BBox, ...]]
    protected_boxes: dict[int, tuple[BBox, ...]]


class BalloonService:
    def __init__(
        self,
        session: Session,
        *,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or LocalFileStorage(get_settings().storage_root)

    def list_for_project(self, project_id: uuid.UUID) -> list[Balloon]:
        return list(
            self.session.scalars(
                select(Balloon)
                .where(Balloon.project_id == project_id)
                .order_by(Balloon.sort_order, Balloon.id)
            )
        )

    def get(self, balloon_id: uuid.UUID) -> Balloon:
        balloon = self.session.get(Balloon, balloon_id)
        if balloon is None:
            raise BalloonNotFound(f"balloon {balloon_id} was not found")
        return balloon

    def get_item(self, inspection_item_id: str) -> dict[str, Any]:
        balloon = self.session.scalar(
            select(Balloon)
            .where(Balloon.inspection_item_id == inspection_item_id)
            .order_by(Balloon.status, Balloon.id)
        )
        if balloon is not None:
            working = self._working_copy(balloon.project_id)
            for item in working.items:
                if item["item_id"] == inspection_item_id:
                    return item
        raise BalloonNotFound(f"inspection item {inspection_item_id} was not found")

    def generate_formal(
        self,
        project_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
    ) -> list[Balloon]:
        working = self._locked_working_copy(project_id, operator_id)
        self._require_working_version(working, expected_version)
        if working.items_frozen_at is None:
            self.session.rollback()
            raise ItemSetNotFrozen("reviewed item set must be frozen first")

        required_items = [
            item
            for item in working.items
            if item.get("active", True) and item.get("balloon_required") is True
        ]
        existing = self._active_balloons(project_id, for_update=True)
        required_ids = {str(item["item_id"]) for item in required_items}
        if existing:
            if {balloon.inspection_item_id for balloon in existing} == required_ids:
                return sorted(existing, key=lambda balloon: balloon.sort_order)
            self.session.rollback()
            raise BalloonOrderConflict(
                "active balloon set differs from the frozen required item set"
            )

        inventory = self._inventory(working)
        geometries = {
            str(item["item_id"]): self._geometry_for_item(item, inventory)
            for item in required_items
        }
        numberable = [
            NumberableItem(
                item_id=str(item["item_id"]),
                balloon_required=True,
                page_index=geometries[str(item["item_id"])].page_index,
                source_bbox=geometries[str(item["item_id"])].anchor_bbox,
                stable_seed=geometries[str(item["item_id"])].source_location_id,
                direction=geometries[str(item["item_id"])].direction,
            )
            for item in required_items
        ]
        suggested = {
            value.item_id: value.number
            for value in assign_suggested_numbers(numberable)
        }
        formal = {
            value.item_id: value.number
            for value in assign_formal_numbers(numberable)
        }
        placements: dict[str, PlacementResult] = {}
        by_page: dict[int, list[PlacementItem]] = {}
        for item_id, number in sorted(formal.items(), key=lambda value: value[1]):
            geometry = geometries[item_id]
            by_page.setdefault(geometry.page_index, []).append(
                self._placement_item(item_id, number, geometry)
            )
        for page_index, placement_items in sorted(by_page.items()):
            for placement in place_balloons(
                tuple(placement_items),
                self._scene(
                    inventory,
                    page_index,
                    source_text_boxes=self._source_text_boxes(working, inventory),
                ),
            ):
                placements[placement.item_id] = placement

        generated: list[Balloon] = []
        for item_id, number in sorted(formal.items(), key=lambda value: value[1]):
            geometry = geometries[item_id]
            placement = placements[item_id]
            balloon = Balloon(
                project_id=project_id,
                inspection_item_id=item_id,
                source_location_id=geometry.source_location_id,
                page_index=geometry.page_index,
                suggested_number=suggested[item_id],
                formal_number=number,
                sort_order=number - 1,
                anchor_bbox_pdf=list(geometry.anchor_bbox),
                leader_target_pdf=list(self._anchor_center(geometry.anchor_bbox)),
                center_pdf=list(placement.center),
                placement_status=placement.status,
                collision_flags=list(placement.collision_flags),
                status="active",
                version=1,
            )
            self.session.add(balloon)
            generated.append(balloon)
        working.numbering_stale = False
        self.session.flush()
        self._record(
            project_id,
            operator_id,
            "generate_balloons",
            [str(balloon.id) for balloon in generated],
            working.version,
            working.version,
        )
        self.session.commit()
        return sorted(generated, key=lambda balloon: balloon.sort_order)

    def move(
        self,
        balloon_id: uuid.UUID,
        *,
        center_pdf: PdfPoint,
        expected_version: int,
        operator_id: str,
    ) -> Balloon:
        balloon = self._locked_balloon(balloon_id, operator_id, active=True)
        self._require_balloon_version(balloon, expected_version)
        center = self._pdf_point(center_pdf)
        working = self._working_copy(balloon.project_id)
        inventory = self._inventory(working)
        item = self._item(working, balloon.inspection_item_id)
        geometry = self._geometry_for_item(item, inventory)
        active = self._active_balloons(balloon.project_id, for_update=True)
        placement = evaluate_placement(
            self._placement_item(
                balloon.inspection_item_id,
                balloon.formal_number or balloon.suggested_number,
                geometry,
            ),
            self._scene(
                inventory,
                balloon.page_index,
                balloons=active,
                exclude_id=balloon.id,
                source_text_boxes=self._source_text_boxes(working, inventory),
            ),
            center,
        )
        before = balloon.version
        balloon.center_pdf = list(center)
        balloon.placement_status = placement.status
        balloon.collision_flags = list(placement.collision_flags)
        balloon.version += 1
        self._record_balloon(balloon, operator_id, "move_balloon", before)
        self.session.flush()
        self._revalidate_positions(working, active)
        self.session.commit()
        return balloon

    def delete(
        self,
        balloon_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
    ) -> Balloon:
        balloon = self._locked_balloon(balloon_id, operator_id, active=True)
        self._require_balloon_version(balloon, expected_version)
        working = self._working_copy(balloon.project_id, for_update=True)
        before = balloon.version
        balloon.status = "deleted"
        balloon.version += 1
        self._record_balloon(balloon, operator_id, "delete_balloon", before)
        self.session.flush()
        self._revalidate_positions(
            working,
            self._active_balloons(balloon.project_id, for_update=True),
        )
        self.session.commit()
        return balloon

    def rebuild(
        self,
        balloon_id: uuid.UUID,
        *,
        expected_version: int,
        operator_id: str,
    ) -> Balloon:
        balloon = self._locked_balloon(balloon_id, operator_id, active=False)
        self._require_balloon_version(balloon, expected_version)
        working = self._working_copy(balloon.project_id, for_update=True)
        item = self._item(working, balloon.inspection_item_id)
        if not item.get("active", True) or item.get("balloon_required") is not True:
            self.session.rollback()
            raise BalloonOrderConflict("reviewed item no longer requires a balloon")
        inventory = self._inventory(working)
        geometry = self._geometry_for_item(item, inventory)
        active_balloons = self._active_balloons(
            balloon.project_id,
            for_update=True,
        )
        placement = place_balloons(
            (
                self._placement_item(
                    balloon.inspection_item_id,
                    balloon.formal_number or balloon.suggested_number,
                    geometry,
                ),
            ),
            self._scene(
                inventory,
                geometry.page_index,
                balloons=active_balloons,
                exclude_id=balloon.id,
                source_text_boxes=self._source_text_boxes(working, inventory),
            ),
        )[0]
        number_reused = balloon.formal_number is None or any(
            active.id != balloon.id
            and active.formal_number == balloon.formal_number
            for active in active_balloons
        )
        before = balloon.version
        balloon.source_location_id = geometry.source_location_id
        balloon.page_index = geometry.page_index
        balloon.anchor_bbox_pdf = list(geometry.anchor_bbox)
        balloon.leader_target_pdf = list(self._anchor_center(geometry.anchor_bbox))
        balloon.center_pdf = list(placement.center)
        balloon.placement_status = placement.status
        balloon.collision_flags = list(placement.collision_flags)
        if number_reused:
            balloon.formal_number = None
            working.numbering_stale = True
        balloon.status = "active"
        balloon.version += 1
        self._record_balloon(balloon, operator_id, "rebuild_balloon", before)
        self.session.flush()
        self._revalidate_positions(
            working,
            self._active_balloons(balloon.project_id, for_update=True),
        )
        self.session.commit()
        return balloon

    def reorder(
        self,
        balloon_id: uuid.UUID,
        *,
        sort_order: int,
        expected_version: int,
        operator_id: str,
    ) -> Balloon:
        if sort_order < 0:
            raise ValueError("sort_order must be non-negative")
        balloon = self._locked_balloon(balloon_id, operator_id, active=True)
        self._require_balloon_version(balloon, expected_version)
        working = self._working_copy(balloon.project_id, for_update=True)
        before = balloon.version
        balloon.sort_order = sort_order
        balloon.version += 1
        working.numbering_stale = True
        self._record_balloon(balloon, operator_id, "reorder_balloon", before)
        self.session.commit()
        return balloon

    def renumber(
        self,
        project_id: uuid.UUID,
        *,
        ordered_balloon_ids: list[uuid.UUID],
        expected_versions: dict[uuid.UUID, int],
        operator_id: str,
    ) -> list[Balloon]:
        working = self._locked_working_copy(project_id, operator_id)
        balloons = self._active_balloons(project_id, for_update=True)
        current = {balloon.id: balloon for balloon in balloons}
        if len(set(ordered_balloon_ids)) != len(ordered_balloon_ids):
            self.session.rollback()
            raise BalloonOrderConflict("renumber IDs must be distinct")
        if set(ordered_balloon_ids) != set(current):
            self.session.rollback()
            raise BalloonOrderConflict("renumber must include every active balloon")
        if set(expected_versions) != set(current):
            self.session.rollback()
            raise BalloonVersionConflict(
                "expected_versions must cover every active balloon"
            )
        for balloon_id, balloon in current.items():
            self._require_balloon_version(balloon, expected_versions[balloon_id])

        for balloon in balloons:
            balloon.formal_number = None
        self.session.flush()
        ordered = [current[balloon_id] for balloon_id in ordered_balloon_ids]
        target_ids: list[str] = []
        for number, balloon in enumerate(ordered, start=1):
            balloon.formal_number = number
            balloon.version += 1
            target_ids.append(str(balloon.id))
        self.session.flush()
        self._revalidate_positions(working, ordered)
        working.numbering_stale = False
        self._record(
            project_id,
            operator_id,
            "renumber_balloons",
            target_ids,
            working.version,
            working.version,
        )
        self.session.commit()
        return ordered

    def validation_blockers(self, project_id: uuid.UUID) -> list[str]:
        working = self._working_copy(project_id)
        inventory = self._inventory(working)
        balloons = self._active_balloons(project_id)
        return validate_balloons(
            working.items,
            balloons,
            inventory.page_sizes,
            protected_boxes=inventory.protected_boxes,
            source_text_boxes=self._source_text_boxes(working, inventory),
        )

    def _locked_balloon(
        self,
        balloon_id: uuid.UUID,
        operator_id: str,
        *,
        active: bool,
    ) -> Balloon:
        preview = self.session.get(Balloon, balloon_id)
        if preview is None or (active and preview.status != "active"):
            self.session.rollback()
            raise BalloonNotFound(f"balloon {balloon_id} was not found")
        self._locked_working_copy(preview.project_id, operator_id)
        balloon = self.session.scalar(
            select(Balloon).where(Balloon.id == balloon_id).with_for_update()
        )
        if balloon is None or (active and balloon.status != "active"):
            self.session.rollback()
            raise BalloonNotFound(f"balloon {balloon_id} was not found")
        return balloon

    def _locked_working_copy(
        self,
        project_id: uuid.UUID,
        operator_id: str,
    ) -> ReviewWorkingCopy:
        require_active_lock(self.session, project_id, operator_id)
        working = self._working_copy(project_id, for_update=True)
        self._require_mutable(project_id)
        return working

    def _require_mutable(self, project_id: uuid.UUID) -> None:
        project = self.session.get(Project, project_id)
        reviewed = self.session.scalar(
            select(ReviewedResult.id).where(
                ReviewedResult.project_id == project_id
            )
        )
        if (
            project is None
            or ProjectState(project.state) != ProjectState.EDITING
            or reviewed is not None
        ):
            self.session.rollback()
            raise BalloonReviewFinalized("balloon review is finalized")

    def _working_copy(
        self,
        project_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ReviewWorkingCopy:
        query = select(ReviewWorkingCopy).where(
            ReviewWorkingCopy.project_id == project_id
        )
        if for_update:
            query = query.with_for_update()
        working = self.session.scalar(query)
        if working is None:
            raise BalloonNotFound(f"working copy for project {project_id} was not found")
        return working

    def _active_balloons(
        self,
        project_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> list[Balloon]:
        query = (
            select(Balloon)
            .where(Balloon.project_id == project_id, Balloon.status == "active")
            .order_by(Balloon.sort_order, Balloon.id)
        )
        if for_update:
            query = query.with_for_update()
        return list(self.session.scalars(query))

    def _inventory(self, working: ReviewWorkingCopy) -> InventoryIndex:
        raw = self.session.get(AutomaticResult, working.raw_result_id)
        if raw is None:
            raise BalloonSourceUnavailable("automatic result was not found")
        try:
            document = json.loads(self.storage.read_bytes(raw.inventory_ref))
            pages = document["pages"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise BalloonSourceUnavailable("page inventory is unavailable") from error

        page_sizes: dict[int, PdfPoint] = {}
        observations: list[tuple[str, int, BBox, PdfPoint, str]] = []
        try:
            for page in pages:
                page_index = int(page["page_index"])
                page_sizes[page_index] = (
                    float(page["width"]),
                    float(page["height"]),
                )
                for observation in page.get("observations", []):
                    observations.append(
                        (
                            str(observation["observation_id"]),
                            page_index,
                            self._pdf_bbox(observation["bbox_pdf"]),
                            self._pdf_point(observation.get("direction", (1, 0))),
                            str(
                                observation.get("normalized_text")
                                or observation.get("raw_text")
                                or ""
                            ).casefold(),
                        )
                    )
        except (KeyError, TypeError, ValueError) as error:
            raise BalloonSourceUnavailable("page inventory geometry is invalid") from error

        geometries: dict[str, SourceGeometry] = {}
        source_text_boxes = {
            page_index: tuple(
                bbox
                for _, observation_page, bbox, _, _ in observations
                if observation_page == page_index
            )
            for page_index in page_sizes
        }
        protected_boxes = {}
        for page_index, (width, height) in page_sizes.items():
            # The selected A3/A4 drawing forms reserve the bottom administration
            # strip for title, revision and sign-off cells, including blank cells.
            registered = (
                0.0,
                height * REGISTERED_ADMINISTRATION_STRIP_START,
                width,
                height,
            )
            keyword_boxes = (
                bbox
                for _, observation_page, bbox, _, text in observations
                if observation_page == page_index
                and any(token in text for token in PROTECTED_TEXT_TOKENS)
            )
            protected_boxes[page_index] = tuple(
                dict.fromkeys((registered, *keyword_boxes))
            )
        for source_id, page_index, bbox, direction, _ in observations:
            forbidden = tuple(
                self._expand(other_bbox, 10.0)
                for other_id, other_page, other_bbox, _, _ in observations
                if other_page == page_index and other_id != source_id
            )
            geometries[source_id] = SourceGeometry(
                source_location_id=source_id,
                page_index=page_index,
                anchor_bbox=bbox,
                direction=direction,
                page_size=page_sizes[page_index],
                forbidden=forbidden,
            )
        return InventoryIndex(
            page_sizes=page_sizes,
            source_geometries=geometries,
            source_text_boxes=source_text_boxes,
            protected_boxes=protected_boxes,
        )

    def _geometry_for_item(
        self,
        item: dict[str, Any],
        inventory: InventoryIndex,
    ) -> SourceGeometry:
        source_ids = item.get("source_location_ids", [])
        if not source_ids:
            raise BalloonSourceUnavailable(
                f"item {item['item_id']} has no source identity"
            )
        source_id = str(source_ids[0])
        geometry = inventory.source_geometries.get(source_id)
        if geometry is not None:
            return geometry
        page_index = item.get("page_index")
        if source_id.startswith("manual:") and isinstance(page_index, int):
            page_size = inventory.page_sizes.get(page_index)
            if page_size is None:
                raise BalloonSourceUnavailable(
                    f"manual item {item['item_id']} references an unknown page"
                )
            return SourceGeometry(
                source_location_id=source_id,
                page_index=page_index,
                anchor_bbox=self._pdf_bbox(item.get("coordinates")),
                direction=(1.0, 0.0),
                page_size=page_size,
                forbidden=tuple(
                    self._expand(value.anchor_bbox, 10.0)
                    for value in inventory.source_geometries.values()
                    if value.page_index == page_index
                ),
            )
        raise BalloonSourceUnavailable(
            f"item {item['item_id']} source {source_id} has no page geometry"
        )

    @staticmethod
    def _placement_item(
        item_id: str,
        formal_number: int,
        geometry: SourceGeometry,
    ) -> PlacementItem:
        return PlacementItem(
            item_id=item_id,
            formal_number=formal_number,
            anchor_bbox=geometry.anchor_bbox,
            page_index=geometry.page_index,
            leader_target=BalloonService._anchor_center(geometry.anchor_bbox),
        )

    def _scene(
        self,
        inventory: InventoryIndex,
        page_index: int,
        *,
        balloons: list[Balloon] | None = None,
        exclude_id: uuid.UUID | None = None,
        source_text_boxes: dict[int, tuple[BBox, ...]] | None = None,
    ) -> PlacementScene:
        occupied: list[OccupiedBalloon] = []
        for balloon in balloons or []:
            if (
                balloon.id == exclude_id
                or balloon.status != "active"
                or balloon.page_index != page_index
            ):
                continue
            center = self._pdf_point(balloon.center_pdf)
            number = balloon.formal_number or balloon.suggested_number
            occupied.append(
                OccupiedBalloon(
                    item_id=balloon.inspection_item_id,
                    formal_number=number,
                    center=center,
                    radius=BALLOON_RADIUS_PDF,
                    glyph_bbox=glyph_bbox(number, center),
                    leader_target=self._pdf_point(balloon.leader_target_pdf),
                )
            )
        return PlacementScene(
            page_size=inventory.page_sizes[page_index],
            source_text_boxes=(source_text_boxes or inventory.source_text_boxes).get(
                page_index,
                (),
            ),
            protected_boxes=inventory.protected_boxes.get(page_index, ()),
            occupied=tuple(occupied),
        )

    def _source_text_boxes(
        self,
        working: ReviewWorkingCopy,
        inventory: InventoryIndex,
    ) -> dict[int, tuple[BBox, ...]]:
        boxes = {
            page_index: list(values)
            for page_index, values in inventory.source_text_boxes.items()
        }
        for item in working.items:
            source_ids = item.get("source_location_ids", [])
            if not any(str(source_id).startswith("manual:") for source_id in source_ids):
                continue
            page_index = item.get("page_index")
            if not isinstance(page_index, int) or isinstance(page_index, bool):
                raise BalloonSourceUnavailable(
                    f"manual item {item['item_id']} has no valid page"
                )
            if page_index not in inventory.page_sizes:
                raise BalloonSourceUnavailable(
                    f"manual item {item['item_id']} references an unknown page"
                )
            bbox = self._pdf_bbox(item.get("coordinates"))
            if bbox not in boxes.setdefault(page_index, []):
                boxes[page_index].append(bbox)
        return {
            page_index: tuple(values)
            for page_index, values in boxes.items()
        }

    def _revalidate_positions(
        self,
        working: ReviewWorkingCopy,
        balloons: list[Balloon],
    ) -> None:
        inventory = self._inventory(working)
        for balloon in balloons:
            item = self._item(working, balloon.inspection_item_id)
            geometry = self._geometry_for_item(item, inventory)
            number = balloon.formal_number or balloon.suggested_number
            placement = evaluate_placement(
                self._placement_item(balloon.inspection_item_id, number, geometry),
                self._scene(
                    inventory,
                    balloon.page_index,
                    balloons=balloons,
                    exclude_id=balloon.id,
                    source_text_boxes=self._source_text_boxes(working, inventory),
                ),
                self._pdf_point(balloon.center_pdf),
            )
            balloon.placement_status = placement.status
            balloon.collision_flags = list(placement.collision_flags)

    @staticmethod
    def _item(
        working: ReviewWorkingCopy,
        inspection_item_id: str,
    ) -> dict[str, Any]:
        for item in working.items:
            if item["item_id"] == inspection_item_id:
                return item
        raise BalloonNotFound(f"inspection item {inspection_item_id} was not found")

    @staticmethod
    def _anchor_center(bbox: BBox) -> PdfPoint:
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

    @staticmethod
    def _expand(bbox: BBox, amount: float) -> BBox:
        return (
            bbox[0] - amount,
            bbox[1] - amount,
            bbox[2] + amount,
            bbox[3] + amount,
        )

    @staticmethod
    def _pdf_point(value: object) -> PdfPoint:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("PDF point must contain two numbers")
        point = (float(value[0]), float(value[1]))
        if not all(math.isfinite(part) for part in point):
            raise ValueError("PDF point must be finite")
        return point

    @staticmethod
    def _pdf_bbox(value: object) -> BBox:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("PDF bbox must contain four numbers")
        bbox = tuple(float(part) for part in value)
        if not all(math.isfinite(part) for part in bbox):
            raise ValueError("PDF bbox must be finite")
        return bbox  # type: ignore[return-value]

    def _require_working_version(
        self,
        working: ReviewWorkingCopy,
        expected_version: int,
    ) -> None:
        if working.version != expected_version:
            self.session.rollback()
            raise BalloonVersionConflict(
                f"expected review version {expected_version}, found {working.version}"
            )

    def _require_balloon_version(
        self,
        balloon: Balloon,
        expected_version: int,
    ) -> None:
        if balloon.version != expected_version:
            self.session.rollback()
            raise BalloonVersionConflict(
                f"expected balloon version {expected_version}, found {balloon.version}"
            )

    def _record_balloon(
        self,
        balloon: Balloon,
        operator_id: str,
        command: str,
        before_version: int,
    ) -> None:
        self._record(
            balloon.project_id,
            operator_id,
            command,
            [str(balloon.id)],
            before_version,
            balloon.version,
        )

    def _record(
        self,
        project_id: uuid.UUID,
        operator_id: str,
        command: str,
        target_ids: list[str],
        before_version: int,
        after_version: int,
    ) -> None:
        self.session.add(
            OperationRecord(
                project_id=project_id,
                operator_id=operator_id,
                command=command,
                target_ids=target_ids,
                before_version=before_version,
                after_version=after_version,
            )
        )
