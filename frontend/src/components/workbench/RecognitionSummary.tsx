import type { BalloonOverlay, ReviewItem } from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import { isAutoAcceptedItem } from "./inspectionItemPresentation";


export type InspectionFilter =
  | "all"
  | "active"
  | "excluded"
  | "auto_accepted"
  | "review_required"
  | "manual_required"
  | "hard_collision";

type RecognitionSummaryProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  pendingSourceCount?: number;
  manualReviewCount?: number;
  filter: InspectionFilter;
  onFilterChange: (filter: InspectionFilter) => void;
};


export function RecognitionSummary({
  items,
  balloons,
  pendingSourceCount = 0,
  manualReviewCount = 0,
  filter,
  onFilterChange,
}: RecognitionSummaryProps) {
  const active = items.filter((item) => item.active).length;
  const excluded = items.length - active;
  const autoAccepted = items.filter(isAutoAcceptedItem).length;
  const manualBalloons = balloons.filter(
    (balloon) =>
      balloon.status !== "deleted" && balloon.placementStatus === "manual_required",
  ).length;
  const hardCollision = balloons.filter(
    (balloon) =>
      balloon.status !== "deleted" && (balloon.collisionFlags?.length ?? 0) > 0,
  ).length;
  const chips: Array<{
    value: InspectionFilter;
    label: string;
    testId: string;
    count: number;
  }> = [
    {
      value: "active",
      label: zhCN.summary.active,
      testId: "summary-active-count",
      count: active,
    },
    {
      value: "excluded",
      label: zhCN.summary.excluded,
      testId: "summary-excluded-count",
      count: excluded,
    },
    {
      value: "auto_accepted",
      label: zhCN.summary.autoAccepted,
      testId: "summary-auto-count",
      count: autoAccepted,
    },
    {
      value: "review_required",
      label: zhCN.summary.reviewRequired,
      testId: "summary-review-count",
      count: manualReviewCount,
    },
    {
      value: "manual_required",
      label: zhCN.summary.manualRequired,
      testId: "summary-manual-count",
      count: manualBalloons,
    },
    {
      value: "hard_collision",
      label: zhCN.summary.hardCollision,
      testId: "summary-collision-count",
      count: hardCollision,
    },
  ];

  return (
    <section
      className="recognition-summary"
      aria-label={zhCN.summary.region}
      role="region"
    >
      <button
        type="button"
        className="summary-chip summary-chip--all"
        data-active={filter === "all"}
        aria-label={zhCN.summary.filter(zhCN.summary.all)}
        onClick={() => onFilterChange("all")}
      >
        <span>{zhCN.summary.all}</span>
        <strong>{items.length + pendingSourceCount}</strong>
      </button>
      {chips.map((chip) => (
        <button
          key={chip.value}
          type="button"
          className={[
            "summary-chip",
            `summary-chip--${chip.value}`,
          ].filter(Boolean).join(" ")}
          data-active={filter === chip.value}
          aria-label={zhCN.summary.filter(chip.label)}
          onClick={() => onFilterChange(chip.value)}
        >
          <span>{chip.label}</span>
          <strong data-testid={chip.testId}>{chip.count}</strong>
        </button>
      ))}
    </section>
  );
}
