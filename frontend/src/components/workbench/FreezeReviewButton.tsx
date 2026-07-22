import type { BalloonOverlay, ReviewWorkingCopy } from "../../api/types";


type FreezeReviewButtonProps = {
  workingCopy: ReviewWorkingCopy;
  balloons: BalloonOverlay[];
  balloonBlockers: string[];
  busy?: boolean;
  onFreeze: () => void;
  onGenerate: () => void;
  onConfirm: () => void;
};


function hasResolvedReview(workingCopy: ReviewWorkingCopy): boolean {
  const blocking = Number(workingCopy.coverage.blocking_count ?? 0);
  const unresolved = Number(workingCopy.coverage.review_required_count ?? 0);
  return (
    blocking === 0 &&
    unresolved === 0 &&
    workingCopy.items
      .filter((item) => item.active)
      .every(
        (item) =>
          item.requires_confirmation !== true && item.balloon_required !== null &&
          item.balloon_required !== undefined,
      )
  );
}


function hasContinuousFormalNumbers(balloons: BalloonOverlay[]): boolean {
  const numbers = balloons
    .filter((balloon) => balloon.status !== "deleted")
    .map((balloon) => balloon.number)
    .sort((left, right) => left - right);
  return numbers.length > 0 && numbers.every((number, index) => number === index + 1);
}


export function FreezeReviewButton({
  workingCopy,
  balloons,
  balloonBlockers,
  busy = false,
  onFreeze,
  onGenerate,
  onConfirm,
}: FreezeReviewButtonProps) {
  const frozen = workingCopy.items_frozen_at !== null;
  const canFreeze = !busy && !frozen && hasResolvedReview(workingCopy);
  const canGenerate = !busy && frozen && balloons.every(
    (balloon) => balloon.status === "deleted",
  );
  const canConfirm =
    !busy &&
    frozen &&
    !workingCopy.numbering_stale &&
    balloonBlockers.length === 0 &&
    hasContinuousFormalNumbers(balloons);

  return (
    <section aria-label="Review finalization" style={{ display: "flex", gap: 8 }}>
      <button type="button" disabled={!canFreeze} onClick={onFreeze}>
        Freeze Items
      </button>
      <button type="button" disabled={!canGenerate} onClick={onGenerate}>
        Generate balloons
      </button>
      <button type="button" disabled={!canConfirm} onClick={onConfirm}>
        Confirm Reviewed Result
      </button>
    </section>
  );
}
