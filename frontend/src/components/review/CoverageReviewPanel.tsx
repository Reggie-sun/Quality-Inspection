import { useEffect, useMemo, useState } from "react";

import type {
  OverlayBox,
  ReviewCommand,
  ReviewCoverageEntry,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import "../../styles/coverage-review.css";


type CoverageReviewPanelProps = {
  entries: ReviewCoverageEntry[];
  sources: OverlayBox[];
  onCommand: (command: ReviewCommand) => void;
  onSelectSource: (sourceId: string) => void;
  selectedSourceId?: string;
  disabled?: boolean;
};


export function CoverageReviewPanel({
  entries,
  sources,
  onCommand,
  onSelectSource,
  selectedSourceId,
  disabled = false,
}: CoverageReviewPanelProps) {
  const unresolved = useMemo(
    () => entries.filter((entry) => entry.requires_confirmation),
    [entries],
  );
  const [cursor, setCursor] = useState(0);
  const selectedIndex = unresolved.findIndex(
    (entry) => entry.source_location_id === selectedSourceId,
  );
  const currentIndex = Math.min(
    selectedIndex >= 0 ? selectedIndex : cursor,
    Math.max(0, unresolved.length - 1),
  );
  const current = unresolved[currentIndex];

  useEffect(() => {
    if (selectedIndex >= 0) setCursor(selectedIndex);
  }, [selectedIndex]);

  useEffect(() => {
    if (
      current !== undefined
      && current.source_location_id !== selectedSourceId
    ) {
      onSelectSource(current.source_location_id);
    }
  }, [current, onSelectSource, selectedSourceId]);

  if (current === undefined) return null;

  const source = sources.find((item) => item.id === current.source_location_id);
  const rawText = source?.rawText?.trim() || zhCN.workbench.unknown;
  const page = source?.pageIndex === undefined
    ? undefined
    : source.pageIndex + 1;
  const selectAt = (nextIndex: number) => {
    const bounded = Math.max(0, Math.min(nextIndex, unresolved.length - 1));
    setCursor(bounded);
    onSelectSource(unresolved[bounded].source_location_id);
  };

  return (
    <section
      aria-label={zhCN.coverageReview.region}
      className="coverage-review-panel"
      role="region"
    >
      <div className="coverage-review-panel__heading">
        <div>
          <h2>{zhCN.coverageReview.title}</h2>
          <p>{zhCN.coverageReview.hint}</p>
        </div>
        <strong aria-live="polite">
          {zhCN.coverageReview.progress(currentIndex + 1, unresolved.length)}
        </strong>
      </div>
      <dl>
        <div>
          <dt>{zhCN.coverageReview.rawText}</dt>
          <dd title={rawText}>{rawText}</dd>
        </div>
        <div>
          <dt>{zhCN.coverageReview.sourcePage}</dt>
          <dd>
            {page === undefined
              ? zhCN.workbench.unknown
              : zhCN.inspection.sourcePage(page)}
          </dd>
        </div>
      </dl>
      <div className="coverage-review-panel__actions">
        <div>
          <button
            type="button"
            disabled={disabled || currentIndex === 0}
            onClick={() => selectAt(currentIndex - 1)}
          >
            {zhCN.coverageReview.previous}
          </button>
          <button
            type="button"
            disabled={disabled || currentIndex === unresolved.length - 1}
            onClick={() => selectAt(currentIndex + 1)}
          >
            {zhCN.coverageReview.next}
          </button>
        </div>
        <div>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onCommand({
              type: "resolve_confirmation",
              item_id: current.observation_id,
              accepted: false,
            })}
          >
            {zhCN.coverageReview.reject}
          </button>
          <button
            type="button"
            className="coverage-review-panel__primary"
            disabled={disabled}
            onClick={() => onCommand({
              type: "resolve_confirmation",
              item_id: current.observation_id,
              accepted: true,
            })}
          >
            {zhCN.coverageReview.accept}
          </button>
        </div>
      </div>
    </section>
  );
}
