import { useEffect, useImperativeHandle, useState } from "react";
import type { Ref } from "react";

import type {
  BalloonOverlay,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import type { DraftSaveHandle } from "./draftSave";
import { inspectionItemPresentation } from "./inspectionItemPresentation";


type SelectedSipDetailFieldsProps = {
  item?: ReviewItem;
  balloon?: BalloonOverlay;
  disabled?: boolean;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onDraftChange?: (dirty: boolean) => void;
  draftSaveRef?: Ref<DraftSaveHandle>;
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
  draftSaveRef,
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

  const clearDraft = (itemId: string) => {
    setDirtyItemIds((current) =>
      current.filter((candidate) => candidate !== itemId),
    );
  };
  const saveDetailDraft = async (itemId: string): Promise<boolean> => {
    const itemDraft = drafts[itemId];
    if (itemDraft === undefined) return false;
    const requiredValues = [
      itemDraft.inspectionItem,
      itemDraft.inspectionStandard,
      itemDraft.inspectionMethod,
      itemDraft.keyDimension,
      itemDraft.inspectionRole,
      itemDraft.sourcePage,
    ];
    const sourcePage = Number(itemDraft.sourcePage);
    if (
      requiredValues.some((value) => value.trim() === "")
      || !Number.isInteger(sourcePage)
      || sourcePage < 1
    ) return false;
    const succeeded = await commandSucceeded(onCommand, {
      type: "set_sip_detail_fields",
      item_id: itemId,
      inspection_item: itemDraft.inspectionItem,
      inspection_standard: itemDraft.inspectionStandard,
      inspection_method: itemDraft.inspectionMethod,
      key_dimension: itemDraft.keyDimension,
      inspection_role: itemDraft.inspectionRole,
      source_page: sourcePage,
      remarks: itemDraft.remarks,
    });
    if (succeeded) clearDraft(itemId);
    return succeeded;
  };

  useImperativeHandle(draftSaveRef, () => ({
    saveDrafts: async () => {
      for (const itemId of [...dirtyItemIds]) {
        if (!(await saveDetailDraft(itemId))) return false;
      }
      return true;
    },
  }));

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
    clearDraft(item.item_id);
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
            await saveDetailDraft(item.item_id);
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
