import { useEffect, useMemo, useState } from "react";

import type { BalloonOverlay, ReviewCommand, ReviewItem } from "../../api/types";
import type { InspectionFilter } from "./RecognitionSummary";


type InspectionItemTableProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  filter: InspectionFilter;
  selectedItemId?: string;
  disabled?: boolean;
  onSelectItem: (itemId: string) => void;
  onCommand?: (command: ReviewCommand) => void;
};

type DetailDraft = {
  inspectionItem: string;
  inspectionStandard: string;
  inspectionMethod: string;
  keyDimension: string;
  inspectionRole: string;
  sourcePage: string;
};


function typeLabel(item: ReviewItem): string {
  return (item.item_type ?? item.coarse_type ?? "untyped").replaceAll("_", " ");
}


function tolerance(item: ReviewItem): string {
  const values = [
    item.upper_tolerance === null || item.upper_tolerance === undefined
      ? ""
      : `+${item.upper_tolerance}`,
    item.lower_tolerance ?? "",
  ].filter(Boolean);
  return values.length === 0 ? "—" : values.join(" / ");
}


function detailDraft(item?: ReviewItem): DetailDraft {
  return {
    inspectionItem: item?.inspection_item ?? "",
    inspectionStandard: item?.inspection_standard ?? "",
    inspectionMethod: item?.inspection_method ?? "",
    keyDimension: item?.key_dimension ?? "",
    inspectionRole: item?.inspection_role ?? "",
    sourcePage: String(item?.source_page ?? ((item?.page_index ?? 0) + 1)),
  };
}


export function InspectionItemTable({
  items,
  balloons,
  filter,
  selectedItemId,
  disabled = false,
  onSelectItem,
  onCommand,
}: InspectionItemTableProps) {
  const balloonByItem = useMemo(
    () => new Map(
      balloons
        .filter((balloon) => balloon.status !== "deleted" && balloon.itemId !== undefined)
        .map((balloon) => [balloon.itemId as string, balloon]),
    ),
    [balloons],
  );
  const visible = items.filter((item) => {
    const balloon = balloonByItem.get(item.item_id);
    if (filter === "active") return item.active;
    if (filter === "excluded") return !item.active;
    if (filter === "manual_required") {
      return balloon?.placementStatus === "manual_required";
    }
    if (filter === "hard_collision") return (balloon?.collisionFlags?.length ?? 0) > 0;
    return true;
  });
  const selected = items.find((item) => item.item_id === selectedItemId);
  const [draft, setDraft] = useState<DetailDraft>(() => detailDraft(selected));
  useEffect(() => setDraft(detailDraft(selected)), [selectedItemId]);

  return (
    <section className="inspection-table-section" aria-label="Inspection items">
      <div className="inspection-table" role="table" aria-label="Inspection item list">
        <div className="inspection-table__head" role="row">
          <span role="columnheader">No.</span>
          <span role="columnheader">Inspection</span>
          <span role="columnheader">Value / tolerance</span>
          <span role="columnheader">Page</span>
          <span role="columnheader">Geometry</span>
        </div>
        <div className="inspection-table__body">
          {visible.length === 0 ? (
            <p className="inspection-table__empty">No items match this filter.</p>
          ) : visible.map((item) => {
            const balloon = balloonByItem.get(item.item_id);
            const collision = balloon?.collisionFlags?.join(", ").replaceAll("_", " ");
            const geometryState = !item.active
              ? "Excluded"
              : balloon?.placementStatus === "manual_required"
                ? "Manual required"
                : collision
                  ? "Hard collision"
                  : balloon === undefined && item.balloon_required
                    ? "Balloon pending"
                    : "Ready";
            return (
              <div
                key={item.item_id}
                role="row"
                tabIndex={0}
                data-selected={selectedItemId === item.item_id}
                data-item-id={item.item_id}
                data-active={item.active}
                className="inspection-table__row"
                onClick={() => onSelectItem(item.item_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    onSelectItem(item.item_id);
                  }
                }}
              >
                <strong role="cell" className="inspection-number">
                  {balloon?.number ?? "—"}
                </strong>
                <span role="cell">
                  <strong>{item.raw_text}</strong>
                  <small>{typeLabel(item)}</small>
                </span>
                <span role="cell">
                  <strong>{item.nominal ?? item.raw_text}</strong>
                  <small>{tolerance(item)}</small>
                </span>
                <span role="cell">Page {(item.page_index ?? balloon?.pageIndex ?? 0) + 1}</span>
                <span role="cell" className={`geometry-state geometry-state--${geometryState.toLowerCase().replaceAll(" ", "-")}`}>
                  <strong>{geometryState}</strong>
                  {collision ? <small>{collision}</small> : null}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {selected === undefined || onCommand === undefined || !selected.active ? null : (
        <fieldset className="sip-detail-fields" disabled={disabled}>
          <legend>Selected item SIP confirmation</legend>
          <label>
            Inspection item
            <input
              aria-label={`SIP inspection item ${selected.item_id}`}
              value={draft.inspectionItem}
              onChange={(event) => setDraft({ ...draft, inspectionItem: event.target.value })}
            />
          </label>
          <label>
            Standard
            <input
              aria-label={`SIP standard ${selected.item_id}`}
              value={draft.inspectionStandard}
              onChange={(event) => setDraft({ ...draft, inspectionStandard: event.target.value })}
            />
          </label>
          <label>
            Method
            <input
              aria-label={`SIP method ${selected.item_id}`}
              value={draft.inspectionMethod}
              onChange={(event) => setDraft({ ...draft, inspectionMethod: event.target.value })}
            />
          </label>
          <label>
            Key dimension
            <input
              aria-label={`SIP key dimension ${selected.item_id}`}
              value={draft.keyDimension}
              onChange={(event) => setDraft({ ...draft, keyDimension: event.target.value })}
            />
          </label>
          <label>
            Role
            <input
              aria-label={`SIP role ${selected.item_id}`}
              value={draft.inspectionRole}
              onChange={(event) => setDraft({ ...draft, inspectionRole: event.target.value })}
            />
          </label>
          <label>
            Source page
            <input
              aria-label={`SIP source page ${selected.item_id}`}
              type="number"
              min={1}
              value={draft.sourcePage}
              onChange={(event) => setDraft({ ...draft, sourcePage: event.target.value })}
            />
          </label>
          <button
            type="button"
            disabled={disabled || Object.values(draft).some((value) => value.trim() === "")}
            onClick={() => onCommand({
              type: "set_sip_detail_fields",
              item_id: selected.item_id,
              inspection_item: draft.inspectionItem,
              inspection_standard: draft.inspectionStandard,
              inspection_method: draft.inspectionMethod,
              key_dimension: draft.keyDimension,
              inspection_role: draft.inspectionRole,
              source_page: Number(draft.sourcePage),
            })}
          >
            Confirm selected SIP fields
          </button>
        </fieldset>
      )}
    </section>
  );
}
