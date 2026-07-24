import { useEffect, useMemo, useState } from "react";

import type {
  BalloonOverlay,
  CandidateType,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import type { InspectionFilter } from "./RecognitionSummary";


type InspectionItemTableProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  candidateNumbers?: ReadonlyMap<string, number>;
  filter: InspectionFilter;
  selectedItemId?: string;
  disabled?: boolean;
  onSelectItem: (itemId: string) => void;
  onCommand?: (command: ReviewCommand) => void;
};

type SelectedInspectionItemSummaryProps = {
  item: ReviewItem;
  balloon?: BalloonOverlay;
  candidateNumber?: number;
};

type DetailDraft = {
  inspectionItem: string;
  inspectionStandard: string;
  inspectionMethod: string;
  keyDimension: string;
  inspectionRole: string;
  sourcePage: string;
};

type ItemStatus =
  | "pending"
  | "confirmed"
  | "candidate"
  | "excluded"
  | "manual"
  | "collision";

const PAGE_SIZE = 50;
const EMPTY_CANDIDATE_NUMBERS: ReadonlyMap<string, number> = new Map();
const TYPE_LABELS: Partial<Record<CandidateType, string>> = {
  ...zhCN.inspection.types,
};
const COARSE_TYPE_LABELS: Readonly<Record<string, string>> = {
  ...zhCN.review.coarseTypes,
};
const COLLISION_LABELS: Readonly<Record<string, string>> = {
  ...zhCN.inspection.collisions,
};
const STATUS_LABELS: Record<ItemStatus, string> = {
  pending: zhCN.inspection.statusPending,
  confirmed: zhCN.inspection.statusConfirmed,
  candidate: zhCN.inspection.statusCandidate,
  excluded: zhCN.inspection.statusExcluded,
  manual: zhCN.inspection.statusManual,
  collision: zhCN.inspection.statusCollision,
};


function typeLabel(item: ReviewItem): string {
  if (item.item_type !== undefined) {
    return TYPE_LABELS[item.item_type] ?? zhCN.workbench.unknown;
  }
  return item.coarse_type === undefined
    ? zhCN.workbench.unknown
    : COARSE_TYPE_LABELS[item.coarse_type] ?? zhCN.workbench.unknown;
}


function tolerance(item: ReviewItem): string {
  const values = [
    item.upper_tolerance === null || item.upper_tolerance === undefined
      ? ""
      : `+${item.upper_tolerance}`,
    item.lower_tolerance ?? "",
  ].filter(Boolean);
  return values.length === 0 ? zhCN.workbench.unknown : values.join(" / ");
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


function itemStatus(item: ReviewItem, balloon?: BalloonOverlay): ItemStatus {
  if (!item.active) return "excluded";
  if (balloon?.placementStatus === "manual_required") return "manual";
  if ((balloon?.collisionFlags?.length ?? 0) > 0) return "collision";
  if (item.requires_confirmation === true || item.status === "pending") {
    return "pending";
  }
  if (item.status === "kept" || item.sip_detail_fields_confirmed === true) {
    return "confirmed";
  }
  return balloon === undefined && item.balloon_required === true
    ? "candidate"
    : "pending";
}


export function SelectedInspectionItemSummary({
  item,
  balloon,
  candidateNumber,
}: SelectedInspectionItemSummaryProps) {
  const numberKind = balloon !== undefined
    ? "formal"
    : candidateNumber !== undefined
      ? "candidate"
      : "empty";
  const displayNumber = balloon?.number
    ?? candidateNumber
    ?? zhCN.workbench.unknown;
  const numberLabel = balloon !== undefined
    ? zhCN.inspection.formalNumber(balloon.number)
    : candidateNumber !== undefined
      ? zhCN.inspection.candidateNumber(candidateNumber)
      : zhCN.inspection.noNumber;
  const page = item.source_page
    ?? (item.page_index === null || item.page_index === undefined
      ? balloon?.pageIndex === undefined
        ? undefined
        : balloon.pageIndex + 1
      : item.page_index + 1);

  return (
    <section
      className="selected-inspection-summary"
      aria-label={zhCN.inspection.selectedItemSummary}
      role="region"
    >
      <dl>
        <div>
          <dt>{zhCN.inspection.balloonNumber}</dt>
          <dd
            className={`selected-inspection-number selected-inspection-number--${numberKind}`}
            aria-label={numberLabel}
          >
            {displayNumber}
          </dd>
        </div>
        <div className="selected-inspection-summary__item">
          <dt>{zhCN.inspection.item}</dt>
          <dd title={item.raw_text}>{item.raw_text}</dd>
        </div>
        <div>
          <dt>{zhCN.inspection.page}</dt>
          <dd>
            {page === undefined
              ? zhCN.workbench.unknown
              : zhCN.inspection.sourcePage(page)}
          </dd>
        </div>
        <div>
          <dt>{zhCN.inspection.status}</dt>
          <dd>{STATUS_LABELS[itemStatus(item, balloon)]}</dd>
        </div>
      </dl>
    </section>
  );
}


export function InspectionItemTable({
  items,
  balloons,
  candidateNumbers = EMPTY_CANDIDATE_NUMBERS,
  filter,
  selectedItemId,
  disabled = false,
  onSelectItem,
  onCommand,
}: InspectionItemTableProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ItemStatus | "all">("all");
  const [page, setPage] = useState(1);
  const balloonByItem = useMemo(
    () => new Map(
      balloons
        .filter((balloon) => balloon.status !== "deleted" && balloon.itemId !== undefined)
        .map((balloon) => [balloon.itemId as string, balloon]),
    ),
    [balloons],
  );
  const filtered = items
    .filter((item) => {
      const balloon = balloonByItem.get(item.item_id);
      const matchesSummary = filter === "active"
        ? item.active
        : filter === "excluded"
          ? !item.active
          : filter === "manual_required"
            ? balloon?.placementStatus === "manual_required"
            : filter === "hard_collision"
              ? (balloon?.collisionFlags?.length ?? 0) > 0
              : true;
      const status = itemStatus(item, balloon);
      const matchesSearch = item.raw_text
        .toLocaleLowerCase("zh-CN")
        .includes(search.trim().toLocaleLowerCase("zh-CN"));
      return matchesSummary
        && (statusFilter === "all" || status === statusFilter)
        && matchesSearch;
    })
    .sort((left, right) => {
      const leftNumber = balloonByItem.get(left.item_id)?.number;
      const rightNumber = balloonByItem.get(right.item_id)?.number;
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
  const pageItems = filtered.slice(pageStart, pageEnd);
  const selectedFilteredIndex = filtered.findIndex(
    (item) => item.item_id === selectedItemId,
  );
  const selectedPage = selectedFilteredIndex < 0
    ? undefined
    : Math.floor(selectedFilteredIndex / PAGE_SIZE) + 1;
  const selected = items.find((item) => item.item_id === selectedItemId);
  const [draft, setDraft] = useState<DetailDraft>(() => detailDraft(selected));

  useEffect(() => setDraft(detailDraft(selected)), [selectedItemId]);
  useEffect(() => setPage(1), [filter, search, statusFilter]);
  useEffect(() => {
    if (selectedPage !== undefined) setPage(selectedPage);
  }, [filter, search, selectedItemId, selectedPage, statusFilter]);

  return (
    <section
      className="inspection-table-section"
      aria-label={zhCN.inspection.region}
    >
      <div className="inspection-list-controls">
        <label>
          <span className="visually-hidden">{zhCN.inspection.search}</span>
          <input
            type="search"
            aria-label={zhCN.inspection.search}
            placeholder={zhCN.inspection.search}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
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
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
      </div>
      <div
        className="inspection-table"
        role="table"
        aria-label={zhCN.inspection.region}
      >
        <div className="inspection-table__head" role="row">
          <span role="columnheader">{zhCN.inspection.number}</span>
          <span role="columnheader">{zhCN.inspection.item}</span>
          <span role="columnheader">{zhCN.inspection.value}</span>
          <span role="columnheader">{zhCN.inspection.page}</span>
          <span role="columnheader">{zhCN.inspection.status}</span>
        </div>
        <div className="inspection-table__body">
          {filtered.length === 0 ? (
            <p className="inspection-table__empty">{zhCN.inspection.empty}</p>
          ) : pageItems.map((item) => {
            const balloon = balloonByItem.get(item.item_id);
            const candidateNumber = candidateNumbers.get(item.item_id);
            const displayNumber = balloon?.number ?? candidateNumber;
            const numberKind = balloon !== undefined
              ? "formal"
              : candidateNumber !== undefined
                ? "candidate"
                : "empty";
            const status = itemStatus(item, balloon);
            const collisions = balloon?.collisionFlags
              ?.map((flag) => COLLISION_LABELS[flag] ?? zhCN.workbench.unknown)
              .join("、");
            return (
              <div
                key={item.item_id}
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
                  className={`inspection-number inspection-number--${numberKind}`}
                  aria-label={
                    balloon === undefined && candidateNumber !== undefined
                      ? zhCN.inspection.candidateNumber(candidateNumber)
                      : undefined
                  }
                >
                  {displayNumber ?? zhCN.workbench.unknown}
                </strong>
                <span role="cell" className="inspection-item-copy">
                  <strong title={item.raw_text}>{item.raw_text}</strong>
                  <small>{typeLabel(item)}</small>
                </span>
                <span role="cell">
                  <strong>{item.nominal ?? item.raw_text}</strong>
                  <small>{tolerance(item)}</small>
                </span>
                <span role="cell">
                  {zhCN.inspection.sourcePage(
                    (item.page_index ?? balloon?.pageIndex ?? 0) + 1,
                  )}
                </span>
                <span role="cell" className={`geometry-state geometry-state--${status}`}>
                  <strong>{STATUS_LABELS[status]}</strong>
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
      {selected === undefined || onCommand === undefined || !selected.active ? null : (
        <fieldset className="sip-detail-fields" disabled={disabled}>
          <legend>{zhCN.inspection.selectedSip}</legend>
          {(
            [
              ["inspectionItem", zhCN.inspection.inspectionItem],
              ["inspectionStandard", zhCN.inspection.standard],
              ["inspectionMethod", zhCN.inspection.method],
              ["keyDimension", zhCN.inspection.keyDimension],
              ["inspectionRole", zhCN.inspection.role],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                aria-label={`${label}：${selected.raw_text}`}
                value={draft[key]}
                onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
              />
            </label>
          ))}
          <label>
            {zhCN.inspection.page}
            <input
              aria-label={`${zhCN.inspection.page}：${selected.raw_text}`}
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
            {zhCN.inspection.confirmSip}
          </button>
        </fieldset>
      )}
    </section>
  );
}
