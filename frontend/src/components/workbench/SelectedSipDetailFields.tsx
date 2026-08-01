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
  onConfirmed?: (itemId: string) => void;
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

type RequiredDetailFieldKey = Exclude<keyof DetailDraft, "remarks">;

const TEXT_DETAIL_FIELDS = [
  ["inspectionItem", zhCN.inspection.inspectionItem],
  ["inspectionStandard", zhCN.inspection.standard],
  ["inspectionMethod", zhCN.inspection.method],
  ["keyDimension", zhCN.inspection.keyDimension],
  ["inspectionRole", zhCN.inspection.role],
] as const;

const REQUIRED_DETAIL_FIELD_KEYS: RequiredDetailFieldKey[] = [
  "inspectionItem",
  "inspectionStandard",
  "inspectionMethod",
  "keyDimension",
  "inspectionRole",
  "sourcePage",
];

const EXCEPTION_FIELDS: Readonly<Record<string, RequiredDetailFieldKey[]>> = {
  composite_method_required: ["inspectionMethod"],
  unsupported_item_type: ["inspectionMethod"],
  missing_inspection_role: ["inspectionRole"],
  missing_source_page: ["sourcePage"],
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
  onConfirmed,
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
  const editableExceptions = item?.sip_mapping_exceptions?.filter(
    (exception) => exception !== "sip_regeneration_required",
  ) ?? [];
  const exceptionMode = editableExceptions.length > 0;
  const exceptionFieldKeys = new Set<RequiredDetailFieldKey>();
  for (const exception of editableExceptions) {
    const mappedFields = EXCEPTION_FIELDS[exception];
    for (const field of mappedFields ?? REQUIRED_DETAIL_FIELD_KEYS) {
      exceptionFieldKeys.add(field);
    }
  }
  for (const field of REQUIRED_DETAIL_FIELD_KEYS) {
    if (draft[field].trim() === "") exceptionFieldKeys.add(field);
  }

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
  useEffect(() => () => {
    onDraftChange?.(false);
  }, [onDraftChange]);

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
    if (succeeded) {
      clearDraft(itemId);
      onConfirmed?.(itemId);
    }
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
  const renderTextField = (
    key: typeof TEXT_DETAIL_FIELDS[number][0],
    label: string,
    exceptionField: boolean,
  ) => (
    <label
      key={key}
      className={exceptionField
        ? "sip-detail-fields__exception-field"
        : undefined}
    >
      <span className="sip-detail-fields__field-label">
        {label}
        {exceptionField ? (
          <small>{zhCN.inspection.exceptionFieldRequired}</small>
        ) : null}
      </span>
      <input
        aria-label={`${label}：${item.raw_text}`}
        value={draft[key]}
        onChange={(event) => {
          updateDraft({ [key]: event.target.value });
        }}
      />
    </label>
  );
  const renderSourcePage = (exceptionField: boolean) => (
    <label
      className={exceptionField
        ? "sip-detail-fields__exception-field"
        : undefined}
    >
      <span className="sip-detail-fields__field-label">
        {zhCN.inspection.page}
        {exceptionField ? (
          <small>{zhCN.inspection.exceptionFieldRequired}</small>
        ) : null}
      </span>
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
  );
  const remarksField = (
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
  );

  return (
    <fieldset className="sip-detail-fields" disabled={disabled}>
      <legend>{zhCN.inspection.selectedSip}</legend>
      {exceptionMode ? (
        <>
          <p className="sip-detail-fields__exception-prompt">
            {zhCN.inspection.exceptionFieldsPrompt}
          </p>
          <div className="sip-detail-fields__exception-fields">
            {TEXT_DETAIL_FIELDS
              .filter(([key]) => exceptionFieldKeys.has(key))
              .map(([key, label]) => renderTextField(key, label, true))}
            {exceptionFieldKeys.has("sourcePage")
              ? renderSourcePage(true)
              : null}
          </div>
          <details className="sip-detail-fields__other-fields">
            <summary>{zhCN.inspection.editOtherSipFields}</summary>
            <div>
              {TEXT_DETAIL_FIELDS
                .filter(([key]) => !exceptionFieldKeys.has(key))
                .map(([key, label]) => renderTextField(key, label, false))}
              {exceptionFieldKeys.has("sourcePage")
                ? null
                : renderSourcePage(false)}
              {remarksField}
            </div>
          </details>
        </>
      ) : (
        <>
          {TEXT_DETAIL_FIELDS.map(([key, label]) =>
            renderTextField(key, label, false)
          )}
          {renderSourcePage(false)}
          {remarksField}
        </>
      )}
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
          {exceptionMode
            ? zhCN.inspection.resolveSipException
            : zhCN.inspection.confirmSip}
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
