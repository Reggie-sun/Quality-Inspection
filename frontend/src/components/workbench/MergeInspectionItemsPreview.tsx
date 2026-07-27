import { useEffect, useId, useRef } from "react";

import type { ReviewItem } from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import { inspectionItemPresentation } from "./inspectionItemPresentation";


export type MergeInspectionItemsPreviewProps = {
  items: ReviewItem[];
  draftRawText: string;
  submitting: boolean;
  onDraftRawTextChange: (value: string) => void;
  onBack: () => void;
  onCancel: () => void;
  onConfirm: () => void;
};


export function suggestMergedRawText(rawTexts: string[]): string {
  return [...new Set(rawTexts.map((value) => value.trim()).filter(Boolean))]
    .join(" ");
}


export function MergeInspectionItemsPreview({
  items,
  draftRawText,
  submitting,
  onDraftRawTextChange,
  onBack,
  onCancel,
  onConfirm,
}: MergeInspectionItemsPreviewProps) {
  const headingId = useId();
  const draftId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const copy = zhCN.review.mergePreview;

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <section
      className="merge-inspection-preview"
      aria-labelledby={headingId}
    >
      <header className="merge-inspection-preview__header">
        <h2 id={headingId} ref={headingRef} tabIndex={-1}>
          {copy.title}
        </h2>
        <p>{copy.explanation}</p>
      </header>

      <div className="merge-inspection-preview__sources">
        <h3>{copy.sources}</h3>
        <ol>
          {items.map((item) => (
            <li key={item.item_id}>
              <span>{item.raw_text}</span>
              <small>{inspectionItemPresentation(item).typeLabel}</small>
            </li>
          ))}
        </ol>
      </div>

      <label
        className="merge-inspection-preview__draft"
        htmlFor={draftId}
      >
        <span>{copy.mergedRawText}</span>
        <textarea
          id={draftId}
          value={draftRawText}
          onChange={(event) => onDraftRawTextChange(event.target.value)}
        />
      </label>

      <div className="merge-inspection-preview__actions">
        <button type="button" disabled={submitting} onClick={onBack}>
          {copy.back}
        </button>
        <button type="button" disabled={submitting} onClick={onCancel}>
          {copy.cancel}
        </button>
        <button
          className="merge-inspection-preview__confirm"
          type="button"
          disabled={
            submitting
            || items.length < 2
            || draftRawText.trim().length === 0
          }
          onClick={onConfirm}
        >
          {copy.confirm(items.length)}
        </button>
      </div>
    </section>
  );
}
