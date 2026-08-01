import { useEffect, useMemo, useRef, useState } from "react";

import type {
  BalloonOverlay,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import {
  INSPECTION_ITEM_STATUS_LABELS,
  inspectionItemPresentation,
  isAutoAcceptedItem,
  isReviewRequiredItem,
} from "./inspectionItemPresentation";
import type { ItemStatus } from "./inspectionItemPresentation";
import type { InspectionFilter } from "./RecognitionSummary";


type InspectionItemTableProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  pendingSources?: PendingSourceReview[];
  candidateNumbers?: ReadonlyMap<string, number>;
  filter: InspectionFilter;
  selectedItemId?: string;
  selectedSourceId?: string;
  compact?: boolean;
  onSelectItem: (itemId: string) => void;
  onSelectSource?: (sourceId: string) => void;
};

export type PendingSourceReview = {
  observationId: string;
  sourceId: string;
  rawText: string;
  coordinates: [number, number, number, number];
  pageIndex?: number;
};

type ListEntry =
  | { kind: "item"; key: string; item: ReviewItem }
  | { kind: "source"; key: string; source: PendingSourceReview };

const PAGE_SIZE = 50;
const EMPTY_CANDIDATE_NUMBERS: ReadonlyMap<string, number> = new Map();
const COLLISION_LABELS: Readonly<Record<string, string>> = {
  ...zhCN.inspection.collisions,
};


function tolerance(item: ReviewItem): string {
  const values = [
    item.upper_tolerance === null || item.upper_tolerance === undefined
      ? ""
      : `+${item.upper_tolerance}`,
    item.lower_tolerance ?? "",
  ].filter(Boolean);
  return values.length === 0 ? zhCN.workbench.unknown : values.join(" / ");
}


export function InspectionItemTable({
  items,
  balloons,
  pendingSources = [],
  candidateNumbers = EMPTY_CANDIDATE_NUMBERS,
  filter,
  selectedItemId,
  selectedSourceId,
  compact = false,
  onSelectItem,
  onSelectSource,
}: InspectionItemTableProps) {
  const [statusFilter, setStatusFilter] = useState<ItemStatus | "all">("all");
  const [page, setPage] = useState(1);
  const tableRef = useRef<HTMLDivElement>(null);
  const balloonByItem = useMemo(
    () => new Map(
      balloons
        .filter((balloon) => balloon.status !== "deleted" && balloon.itemId !== undefined)
        .map((balloon) => [balloon.itemId as string, balloon]),
    ),
    [balloons],
  );
  const entries: ListEntry[] = [
    ...items.map((item) => ({
      kind: "item" as const,
      key: `item:${item.item_id}`,
      item,
    })),
    ...pendingSources.map((source) => ({
      kind: "source" as const,
      key: `source:${source.observationId}`,
      source,
    })),
  ];
  const filtered = entries
    .filter((entry) => {
      if (entry.kind === "source") {
        const matchesSummary =
          filter === "all" || filter === "review_required";
        const matchesStatus =
          statusFilter === "all" || statusFilter === "source_pending";
        return matchesSummary && matchesStatus;
      }
      const item = entry.item;
      const balloon = balloonByItem.get(item.item_id);
      const matchesSummary = filter === "active"
        ? item.active
        : filter === "excluded"
          ? !item.active
          : filter === "auto_accepted"
            ? isAutoAcceptedItem(item)
            : filter === "review_required"
              ? isReviewRequiredItem(item)
              : filter === "manual_required"
                ? balloon?.placementStatus === "manual_required"
                : filter === "hard_collision"
                  ? (balloon?.collisionFlags?.length ?? 0) > 0
                  : true;
      const status = inspectionItemPresentation(item, balloon).status;
      return matchesSummary
        && (statusFilter === "all" || status === statusFilter);
    })
    .sort((left, right) => {
      if (left.kind === "source" && right.kind === "source") return 0;
      if (left.kind === "source") return 1;
      if (right.kind === "source") return -1;
      const leftNumber = balloonByItem.get(left.item.item_id)?.number;
      const rightNumber = balloonByItem.get(right.item.item_id)?.number;
      if (leftNumber !== undefined && rightNumber !== undefined) {
        return leftNumber - rightNumber;
      }
      if (leftNumber !== undefined) return -1;
      if (rightNumber !== undefined) return 1;
      return 0;
    });
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const pageEnd = safePage * PAGE_SIZE;
  const pageEntries = filtered.slice(pageStart, pageEnd);
  const selectedFilteredIndex = filtered.findIndex((entry) =>
    entry.kind === "item"
      ? entry.item.item_id === selectedItemId
      : entry.source.sourceId === selectedSourceId,
  );
  const selectedPage = selectedFilteredIndex < 0
    ? undefined
    : Math.floor(selectedFilteredIndex / PAGE_SIZE) + 1;
  useEffect(() => setPage(1), [filter, statusFilter]);
  useEffect(() => {
    if (selectedPage !== undefined) setPage(selectedPage);
  }, [
    filter,
    selectedItemId,
    selectedPage,
    selectedSourceId,
    statusFilter,
  ]);
  useEffect(() => {
    const selectedRow = tableRef.current
      ?.querySelector<HTMLElement>("[role='row'][data-selected='true']");
    selectedRow?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [safePage, selectedItemId, selectedSourceId]);
  return (
    <section
      className={[
        "inspection-table-section",
        compact ? "inspection-table-section--compact" : "",
      ].filter(Boolean).join(" ")}
      aria-label={zhCN.inspection.region}
    >
      <div className="inspection-list-controls">
        <label>
          <span className="visually-hidden">{zhCN.inspection.statusFilter}</span>
          <select
            aria-label={zhCN.inspection.statusFilter}
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value as ItemStatus | "all");
            }}
          >
            <option value="all">{zhCN.inspection.allStatuses}</option>
            {Object.entries(INSPECTION_ITEM_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
      </div>
      <div
        ref={tableRef}
        className="inspection-table"
        role="table"
        aria-label={zhCN.inspection.region}
      >
        <div className="inspection-table__head" role="row">
          <span role="columnheader">{zhCN.inspection.number}</span>
          <span role="columnheader">{zhCN.inspection.item}</span>
          {compact
            ? null
            : <span role="columnheader">{zhCN.inspection.value}</span>}
          {compact
            ? null
            : <span role="columnheader">{zhCN.inspection.page}</span>}
          <span role="columnheader">{zhCN.inspection.status}</span>
        </div>
        <div className="inspection-table__body">
          {filtered.length === 0 ? (
            <p className="inspection-table__empty">{zhCN.inspection.empty}</p>
          ) : pageEntries.map((entry) => {
            if (entry.kind === "source") {
              const source = entry.source;
              return (
                <div
                  key={entry.key}
                  role="row"
                  tabIndex={0}
                  aria-selected={selectedSourceId === source.sourceId}
                  data-selected={selectedSourceId === source.sourceId}
                  data-source-id={source.sourceId}
                  className="inspection-table__row inspection-table__row--source"
                  onClick={() => onSelectSource?.(source.sourceId)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      onSelectSource?.(source.sourceId);
                    }
                  }}
                >
                  <strong
                    role="cell"
                    className="inspection-number inspection-number--empty"
                  >
                    {zhCN.workbench.unknown}
                  </strong>
                  <span role="cell" className="inspection-item-copy">
                    <strong title={source.rawText || zhCN.workbench.unknown}>{source.rawText || zhCN.workbench.unknown}</strong>
                    <small>{zhCN.inspection.sourceType}</small>
                  </span>
                  {compact
                    ? null
                    : <span role="cell">{zhCN.workbench.unknown}</span>}
                  {compact ? null : (
                    <span role="cell">
                      {source.pageIndex === undefined
                        ? zhCN.workbench.unknown
                        : zhCN.inspection.sourcePage(source.pageIndex + 1)}
                    </span>
                  )}
                  <span
                    role="cell"
                    className="geometry-state geometry-state--source_pending"
                  >
                    <strong>{zhCN.inspection.sourcePending}</strong>
                  </span>
                </div>
              );
            }
            const item = entry.item;
            const balloon = balloonByItem.get(item.item_id);
            const candidateNumber = candidateNumbers.get(item.item_id);
            const presentation = inspectionItemPresentation(
              item,
              balloon,
              candidateNumber,
            );
            const collisions = balloon?.collisionFlags
              ?.map((flag) => COLLISION_LABELS[flag] ?? zhCN.workbench.unknown)
              .join("、");
            return (
              <div
                key={entry.key}
                role="row"
                tabIndex={0}
                aria-selected={selectedItemId === item.item_id}
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
                <strong
                  role="cell"
                  className={[
                    "inspection-number",
                    `inspection-number--${presentation.numberKind}`,
                    presentation.status === "auto_accepted"
                      ? "inspection-number--auto_accepted"
                      : "",
                  ].filter(Boolean).join(" ")}
                  aria-label={
                    presentation.numberKind === "candidate"
                      ? presentation.numberLabel
                      : undefined
                  }
                >
                  {presentation.displayNumber ?? zhCN.workbench.unknown}
                </strong>
                <span role="cell" className="inspection-item-copy">
                  <strong title={item.raw_text}>{item.raw_text}</strong>
                  <small>{presentation.typeLabel}</small>
                </span>
                {compact ? null : (
                  <span role="cell">
                    <strong>{item.nominal ?? item.raw_text}</strong>
                    <small>{tolerance(item)}</small>
                  </span>
                )}
                {compact ? null : (
                  <span role="cell">
                    {presentation.pageLabel}
                  </span>
                )}
                <span
                  role="cell"
                  className={`geometry-state geometry-state--${presentation.status}`}
                >
                  <strong>{presentation.statusLabel}</strong>
                  {collisions ? <small>{collisions}</small> : null}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <nav className="compact-pagination" aria-label={zhCN.inspection.pagination}>
        <button
          type="button"
          aria-label={zhCN.inspection.previousPage}
          disabled={safePage === 1}
          onClick={() => setPage((current) => Math.max(1, current - 1))}
        >
          {zhCN.inspection.previousPage}
        </button>
        <span>{zhCN.inspection.pageLabel(safePage, pageCount)}</span>
        <button
          type="button"
          aria-label={zhCN.inspection.nextPage}
          disabled={safePage === pageCount}
          onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
        >
          {zhCN.inspection.nextPage}
        </button>
      </nav>
    </section>
  );
}
