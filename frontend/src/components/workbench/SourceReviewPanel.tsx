import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type { Ref } from "react";

import type { CandidateType, ReviewCommand } from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import type { DraftSaveHandle } from "./draftSave";
import { INSPECTION_ITEM_TYPE_LABELS } from "./inspectionItemPresentation";
import type { PendingSourceReview } from "./InspectionItemTable";

type SourceDraft = {
  rawText: string;
  itemType: CandidateType | "";
  scope: "local_feature" | "global_requirement";
  balloonRequired: boolean;
};

type SourceReviewPanelProps = {
  pendingSources: PendingSourceReview[];
  selectedSourceId?: string;
  disabled?: boolean;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onDraftChange?: (dirty: boolean) => void;
  draftSaveRef?: Ref<DraftSaveHandle>;
};

function sourceDraft(source: PendingSourceReview): SourceDraft {
  return {
    rawText: source.rawText,
    itemType: "",
    scope: "local_feature",
    balloonRequired: true,
  };
}

async function commandSucceeded(
  onCommand: SourceReviewPanelProps["onCommand"],
  command: ReviewCommand,
): Promise<boolean> {
  return (await onCommand(command)) !== false;
}

export function SourceReviewPanel({
  pendingSources,
  selectedSourceId,
  disabled = false,
  onCommand,
  onDraftChange,
  draftSaveRef,
}: SourceReviewPanelProps) {
  const selectedSource = pendingSources.find((source) =>
    source.sourceId === selectedSourceId);
  const selectedSourceBaseline = selectedSource && sourceDraft(selectedSource);
  const [sourceDrafts, setSourceDrafts] = useState<Record<string, SourceDraft>>(
    () => selectedSource === undefined ? {} : {
      [selectedSource.observationId]: sourceDraft(selectedSource),
    },
  );
  const [dirtySourceIds, setDirtySourceIds] = useState<string[]>([]);
  const [itemTypeRequired, setItemTypeRequired] = useState(false);
  const itemTypeRef = useRef<HTMLSelectElement>(null);
  const selectedSourceDraft = selectedSource && (
    sourceDrafts[selectedSource.observationId] ?? selectedSourceBaseline);

  useEffect(() => {
    if (
      selectedSource === undefined
      || dirtySourceIds.includes(selectedSource.observationId)
    ) return;
    setSourceDrafts((current) => ({
      ...current,
      [selectedSource.observationId]: sourceDraft(selectedSource),
    }));
  }, [selectedSource?.observationId, selectedSource?.rawText, selectedSourceId]);
  useEffect(() => {
    onDraftChange?.(dirtySourceIds.length > 0);
  }, [dirtySourceIds, onDraftChange]);
  useEffect(() => {
    setItemTypeRequired(false);
  }, [selectedSource?.observationId]);

  const updateSourceDraft = (change: Partial<SourceDraft>) => {
    if (selectedSource === undefined || selectedSourceBaseline === undefined) {
      return;
    }
    setSourceDrafts((current) => ({
      ...current,
      [selectedSource.observationId]: {
        ...(current[selectedSource.observationId] ?? selectedSourceBaseline),
        ...change,
      },
    }));
    setDirtySourceIds((current) =>
      current.includes(selectedSource.observationId)
        ? current
        : [...current, selectedSource.observationId],
    );
  };
  const clearSelectedSourceDirty = () => {
    if (selectedSource === undefined) return;
    setDirtySourceIds((current) =>
      current.filter((observationId) =>
        observationId !== selectedSource.observationId),
    );
  };
  const saveSourceDraft = async (
    source: PendingSourceReview,
  ): Promise<boolean> => {
    const draft = sourceDrafts[source.observationId] ?? sourceDraft(source);
    if (
      draft.itemType === ""
      || source.pageIndex === undefined
      || draft.rawText.trim() === ""
    ) return false;
    const succeeded = await commandSucceeded(onCommand, {
      type: "promote_source",
      observation_id: source.observationId,
      raw_text: draft.rawText,
      item_type: draft.itemType,
      scope: draft.scope,
      balloon_required: draft.balloonRequired,
      page_index: source.pageIndex,
    });
    if (succeeded) {
      setDirtySourceIds((current) =>
        current.filter((observationId) => observationId !== source.observationId),
      );
    }
    return succeeded;
  };

  useImperativeHandle(draftSaveRef, () => ({
    saveDrafts: async () => {
      for (const observationId of [...dirtySourceIds]) {
        const source = pendingSources.find(
          (candidate) => candidate.observationId === observationId,
        );
        if (source === undefined || !(await saveSourceDraft(source))) return false;
      }
      return true;
    },
  }));

  if (selectedSource === undefined || selectedSourceDraft === undefined) {
    return null;
  }

  return (
    <fieldset className="source-review-fields" disabled={disabled}>
      <legend className="visually-hidden">
        {zhCN.inspection.sourceEditor}
      </legend>
      <header className="source-review-header">
        <div>
          <h3>{zhCN.inspection.sourceEditor}</h3>
          <p>{zhCN.inspection.sourceEditorHint}</p>
        </div>
        <span className="source-review-status">
          {zhCN.inspection.sourcePending}
        </span>
      </header>
      <div className="source-review-grid">
        <label className="source-review-field">
          <span>{zhCN.inspection.sourceRawText}</span>
          <input
            aria-label={zhCN.inspection.sourceRawText}
            value={selectedSourceDraft.rawText}
            onChange={(event) =>
              updateSourceDraft({ rawText: event.target.value })}
          />
        </label>
        <label className="source-review-field">
          <span>{zhCN.inspection.sourceItemType}</span>
          <select
            ref={itemTypeRef}
            aria-label={zhCN.inspection.sourceItemType}
            aria-invalid={itemTypeRequired || undefined}
            aria-describedby={itemTypeRequired
              ? "source-review-item-type-error"
              : undefined}
            value={selectedSourceDraft.itemType}
            onChange={(event) => {
              setItemTypeRequired(false);
              updateSourceDraft({
                itemType: event.target.value as CandidateType | "",
              });
            }}
          >
            <option value="">{zhCN.inspection.selectItemType}</option>
            {Object.entries(INSPECTION_ITEM_TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          {itemTypeRequired ? (
            <small
              id="source-review-item-type-error"
              className="source-review-field__error"
              role="alert"
            >
              {zhCN.inspection.selectItemType}
            </small>
          ) : null}
        </label>
        <label className="source-review-field">
          <span>{zhCN.inspection.sourceScope}</span>
          <select
            aria-label={zhCN.inspection.sourceScope}
            value={selectedSourceDraft.scope}
            onChange={(event) =>
              updateSourceDraft({
                scope: event.target.value as SourceDraft["scope"],
              })}
          >
            <option value="local_feature">{zhCN.review.localFeature}</option>
            <option value="global_requirement">
              {zhCN.review.globalRequirement}
            </option>
          </select>
        </label>
        <label className="source-review-toggle">
          <span>
            <strong>{zhCN.inspection.sourceBalloonRequired}</strong>
            <small>{zhCN.inspection.sourceBalloonHint}</small>
          </span>
          <input
            aria-label={zhCN.inspection.sourceBalloonRequired}
            type="checkbox"
            checked={selectedSourceDraft.balloonRequired}
            onChange={(event) =>
              updateSourceDraft({ balloonRequired: event.target.checked })}
          />
        </label>
      </div>
      <div className="source-review-actions">
        <button
          className="source-review-actions__secondary"
          type="button"
          disabled={disabled}
          onClick={async () => {
            const succeeded = await commandSucceeded(onCommand, {
              type: "ignore_source",
              observation_id: selectedSource.observationId,
            });
            if (succeeded) clearSelectedSourceDirty();
          }}
        >
          {zhCN.inspection.ignoreSource}
        </button>
        <button
          className="source-review-actions__primary"
          type="button"
          disabled={
            disabled
            || selectedSource.pageIndex === undefined
            || selectedSourceDraft.rawText.trim() === ""
          }
          onClick={async () => {
            if (selectedSourceDraft.itemType === "") {
              setItemTypeRequired(true);
              itemTypeRef.current?.focus();
              return;
            }
            await saveSourceDraft(selectedSource);
          }}
        >
          {selectedSourceDraft.balloonRequired
            ? zhCN.inspection.promoteSourceWithBalloon
            : zhCN.inspection.promoteSourceWithoutBalloon}
        </button>
      </div>
    </fieldset>
  );
}
