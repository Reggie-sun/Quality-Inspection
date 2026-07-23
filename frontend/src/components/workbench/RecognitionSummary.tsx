import type { BalloonOverlay, ReviewItem } from "../../api/types";


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
    { value: "active", label: "Active", testId: "summary-active-count", count: active },
    {
      value: "excluded",
      label: "Excluded",
      testId: "summary-excluded-count",
      count: excluded,
    },
    {
      value: "manual_required",
      label: "Manual required",
      testId: "summary-manual-count",
      count: manual,
    },
    {
      value: "hard_collision",
      label: "Hard collision",
      testId: "summary-collision-count",
      count: hardCollision,
    },
  ];

  return (
    <section className="recognition-summary" aria-label="Recognition summary">
      <button
        type="button"
        className="summary-chip summary-chip--all"
        data-active={filter === "all"}
        aria-label="Filter all inspection items"
        onClick={() => onFilterChange("all")}
      >
        <span>Detected</span>
        <strong>{items.length}</strong>
      </button>
      {chips.map((chip) => (
        <button
          key={chip.value}
          type="button"
          className={`summary-chip summary-chip--${chip.value}`}
          data-active={filter === chip.value}
          aria-label={`Filter ${chip.label.toLowerCase()}`}
          onClick={() => onFilterChange(chip.value)}
        >
          <span>{chip.label}</span>
          <strong data-testid={chip.testId}>{chip.count}</strong>
        </button>
      ))}
    </section>
  );
}
