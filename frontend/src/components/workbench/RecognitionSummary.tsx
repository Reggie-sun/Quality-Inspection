import type { BalloonOverlay, ReviewItem } from "../../api/types";
import { zhCN } from "../../copy/zhCN";


export type InspectionFilter =
  | "all"
  | "active"
  | "excluded"
  | "manual_required"
  | "hard_collision";

type RecognitionSummaryProps = {
  items: ReviewItem[];
  balloons: BalloonOverlay[];
  filter: InspectionFilter;
  onFilterChange: (filter: InspectionFilter) => void;
};


export function RecognitionSummary({
  items,
  balloons,
  filter,
  onFilterChange,
}: RecognitionSummaryProps) {
  const active = items.filter((item) => item.active).length;
  const excluded = items.length - active;
  const manual = balloons.filter(
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
      value: "manual_required",
      label: zhCN.summary.manualRequired,
      testId: "summary-manual-count",
      count: manual,
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
        <strong>{items.length}</strong>
      </button>
      {chips.map((chip) => (
        <button
          key={chip.value}
          type="button"
          className={`summary-chip summary-chip--${chip.value}`}
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
