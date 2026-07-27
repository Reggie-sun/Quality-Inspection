import { useEffect, useState } from "react";

import type {
  BalloonOverlay,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import { inspectionItemPresentation } from "./inspectionItemPresentation";


type SelectedSipDetailFieldsProps = {
  item?: ReviewItem;
  balloon?: BalloonOverlay;
  disabled?: boolean;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onDraftChange?: (dirty: boolean) => void;
};

type DetailDraft = {
  inspectionItem: string;
  inspectionStandard: string;
  inspectionMethod: string;
  keyDimension: string;
  inspectionRole: string;
  sourcePage: string;
  remarks: string;
};


function detailDraft(
  item?: ReviewItem,
  balloon?: BalloonOverlay,
): DetailDraft {
  return {
    inspectionItem: item?.inspection_item ?? "",
    inspectionStandard: item?.inspection_standard ?? "",
    inspectionMethod: item?.inspection_method ?? "",
    keyDimension: item?.key_dimension ?? "",
    inspectionRole: item?.inspection_role ?? "",
    sourcePage: item === undefined
      ? ""
      : inspectionItemPresentation(item, balloon).page?.toString() ?? "",
    remarks: item?.remarks ?? "",
  };
}

async function commandSucceeded(
  onCommand: SelectedSipDetailFieldsProps["onCommand"],
  command: ReviewCommand,
): Promise<boolean> {
  return (await onCommand(command)) !== false;
}


export function SelectedSipDetailFields({
  item,
  balloon,
  disabled = false,
  onCommand,
  onDraftChange,
}: SelectedSipDetailFieldsProps) {
  const baseline = detailDraft(item, balloon);
  const [drafts, setDrafts] = useState<Record<string, DetailDraft>>(
    () => item === undefined
      ? {}
      : { [item.item_id]: baseline },
  );
  const [dirtyItemIds, setDirtyItemIds] = useState<string[]>([]);
  const draft = item === undefined
    ? baseline
    : drafts[item.item_id] ?? baseline;

  useEffect(() => {
    if (item === undefined || dirtyItemIds.includes(item.item_id)) return;
    setDrafts((current) => ({
      ...current,
      [item.item_id]: detailDraft(item, balloon),
    }));
  }, [balloon, item]);
  useEffect(() => {
    onDraftChange?.(dirtyItemIds.length > 0);
  }, [dirtyItemIds, onDraftChange]);

  if (item === undefined || !item.active) return null;

  const updateDraft = (change: Partial<DetailDraft>) => {
    setDrafts((current) => ({
      ...current,
      [item.item_id]: {
        ...(current[item.item_id] ?? baseline),
        ...change,
      },
    }));
    setDirtyItemIds((current) =>
      current.includes(item.item_id)
        ? current
        : [...current, item.item_id],
    );
  };
  const clearSelectedDraft = () => {
    setDirtyItemIds((current) =>
      current.filter((candidate) => candidate !== item.item_id),
    );
  };

  return (
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
            aria-label={`${label}：${item.raw_text}`}
            value={draft[key]}
            onChange={(event) => {
              updateDraft({ [key]: event.target.value });
            }}
          />
        </label>
      ))}
      <label>
        {zhCN.inspection.page}
        <input
          aria-label={`${zhCN.inspection.page}：${item.raw_text}`}
          type="number"
          min={1}
          value={draft.sourcePage}
          onChange={(event) => {
            updateDraft({ sourcePage: event.target.value });
          }}
        />
      </label>
      <label>
        {zhCN.inspection.remarks}
        <textarea
          aria-label={`${zhCN.inspection.remarks}：${item.raw_text}`}
          maxLength={2000}
          rows={3}
          value={draft.remarks}
          onChange={(event) => {
            updateDraft({ remarks: event.target.value });
          }}
        />
      </label>
      <div className="sip-detail-actions">
        <button
          type="button"
          disabled={disabled || [
            draft.inspectionItem,
            draft.inspectionStandard,
            draft.inspectionMethod,
            draft.keyDimension,
            draft.inspectionRole,
            draft.sourcePage,
          ].some((value) => value.trim() === "")}
          onClick={async () => {
            const succeeded = await commandSucceeded(onCommand, {
              type: "set_sip_detail_fields",
              item_id: item.item_id,
              inspection_item: draft.inspectionItem,
              inspection_standard: draft.inspectionStandard,
              inspection_method: draft.inspectionMethod,
              key_dimension: draft.keyDimension,
              inspection_role: draft.inspectionRole,
              source_page: Number(draft.sourcePage),
              remarks: draft.remarks,
            });
            if (succeeded) clearSelectedDraft();
          }}
        >
          {zhCN.inspection.confirmSip}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            setDrafts((current) => ({
              ...current,
              [item.item_id]: detailDraft(item, balloon),
            }));
            clearSelectedDraft();
          }}
        >
          {zhCN.inspection.cancelSip}
        </button>
      </div>
    </fieldset>
  );
}
