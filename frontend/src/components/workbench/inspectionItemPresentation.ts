import type {
  BalloonOverlay,
  CandidateType,
  ProjectWorkbenchCandidateView,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";


export type ItemStatus =
  | "pending"
  | "auto_accepted"
  | "confirmed"
  | "candidate"
  | "excluded"
  | "manual"
  | "collision"
  | "source_pending";

export type InspectionItemPresentation = {
  displayNumber?: number;
  numberKind: "formal" | "candidate" | "empty";
  numberLabel: string;
  typeLabel: string;
  page?: number;
  pageLabel: string;
  status: ItemStatus;
  statusLabel: string;
};

export const INSPECTION_ITEM_TYPE_LABELS: Partial<
  Record<CandidateType, string>
> = {
  ...zhCN.inspection.types,
};

export const INSPECTION_ITEM_STATUS_LABELS: Record<ItemStatus, string> = {
  pending: zhCN.inspection.statusPending,
  auto_accepted: zhCN.inspection.statusAutoAccepted,
  confirmed: zhCN.inspection.statusConfirmed,
  candidate: zhCN.inspection.statusCandidate,
  excluded: zhCN.inspection.statusExcluded,
  manual: zhCN.inspection.statusManual,
  collision: zhCN.inspection.statusCollision,
  source_pending: zhCN.inspection.sourcePending,
};

const COARSE_TYPE_LABELS: Readonly<Record<string, string>> = {
  ...zhCN.review.coarseTypes,
};


function inspectionItemTypeLabel(item: ReviewItem): string {
  if (item.item_type !== undefined) {
    return INSPECTION_ITEM_TYPE_LABELS[item.item_type]
      ?? zhCN.workbench.unknown;
  }
  return item.coarse_type === undefined
    ? zhCN.workbench.unknown
    : COARSE_TYPE_LABELS[item.coarse_type] ?? zhCN.workbench.unknown;
}


function inspectionItemSourcePage(
  item: ReviewItem,
  balloon?: BalloonOverlay,
): number | undefined {
  if (item.source_page !== null && item.source_page !== undefined) {
    return item.source_page;
  }
  if (item.page_index !== null && item.page_index !== undefined) {
    return item.page_index + 1;
  }
  return balloon?.pageIndex === undefined ? undefined : balloon.pageIndex + 1;
}


function inspectionItemStatus(
  item: ReviewItem,
  balloon?: BalloonOverlay,
): ItemStatus {
  if (!item.active) return "excluded";
  if (balloon?.placementStatus === "manual_required") return "manual";
  if ((balloon?.collisionFlags?.length ?? 0) > 0) return "collision";
  if (item.requires_confirmation === true || item.status === "pending") {
    return "pending";
  }
  if (isBalloonDecisionPending(item)) return "pending";
  if (isAutoAcceptedItem(item)) return "auto_accepted";
  if (item.status === "kept" || item.sip_detail_fields_confirmed === true) {
    return "confirmed";
  }
  return "pending";
}

export function isAutoAcceptedItem(item: ReviewItem): boolean {
  return item.active === true
    && item.status === "auto_accepted"
    && item.requires_confirmation === false
    && item.acceptance_source === "confidence_policy"
    && item.confidence_decision?.band === "high"
    && item.confidence_decision.review_disposition === "auto_accepted"
    && item.confidence_decision.policy_version === "candidate-confidence/1";
}

export function isBalloonDecisionPending(item: ReviewItem): boolean {
  const inspectionDecisionResolved =
    item.status === "kept"
    || item.sip_detail_fields_confirmed === true
    || isAutoAcceptedItem(item);
  return item.active === true
    && item.requires_confirmation !== true
    && inspectionDecisionResolved
    && (item.balloon_required === null || item.balloon_required === undefined);
}

export function isAutoAcceptedCandidateProjection(
  item: ReviewItem,
  candidate: ProjectWorkbenchCandidateView,
): boolean {
  return isAutoAcceptedItem(item)
    && candidate.confidence_band === "high"
    && candidate.review_disposition === "auto_accepted"
    && candidate.status === "auto_accepted";
}

export function isReviewRequiredItem(item: ReviewItem): boolean {
  if (!item.active) return false;
  if (item.requires_confirmation === true) return true;
  if (isBalloonDecisionPending(item)) return true;
  if (isAutoAcceptedItem(item)) return false;
  return item.status !== "kept";
}

export function inspectionItemPresentation(
  item: ReviewItem,
  balloon?: BalloonOverlay,
  candidateNumber?: number,
): InspectionItemPresentation {
  const displayNumber = balloon?.number ?? candidateNumber;
  const page = inspectionItemSourcePage(item, balloon);
  const status = inspectionItemStatus(item, balloon);
  const numberKind = balloon !== undefined
    ? "formal"
    : candidateNumber !== undefined
      ? "candidate"
      : "empty";
  const autoAccepted = isAutoAcceptedItem(item);

  return {
    displayNumber,
    numberKind,
    numberLabel: balloon !== undefined
      ? zhCN.inspection.formalNumber(balloon.number)
      : candidateNumber !== undefined
        ? autoAccepted
          ? zhCN.inspection.autoAcceptedCandidateNumber(candidateNumber)
          : zhCN.inspection.candidateNumber(candidateNumber)
        : zhCN.inspection.noNumber,
    typeLabel: inspectionItemTypeLabel(item),
    page,
    pageLabel: page === undefined
      ? zhCN.workbench.unknown
      : zhCN.inspection.sourcePage(page),
    status,
    statusLabel: isBalloonDecisionPending(item)
      ? zhCN.inspection.statusBalloonPending
      : item.scope === "global_requirement"
          && (item.requires_confirmation === true || item.status === "pending")
        ? zhCN.inspection.statusGlobalSipPending
      : INSPECTION_ITEM_STATUS_LABELS[status],
  };
}
