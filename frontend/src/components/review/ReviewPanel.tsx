import { useEffect, useMemo, useRef, useState } from "react";

import type {
  CandidateType,
  PdfCoordinates,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import type { InspectionItemPresentation } from "../workbench/inspectionItemPresentation";


type ReviewPanelProps = {
  items: ReviewItem[];
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  disabled?: boolean;
  selectedItemId?: string;
  selectedItemPresentation?: InspectionItemPresentation;
  onSelectItem?: (itemId: string) => void;
  pageIndex?: number;
  onDraftChange?: (dirty: boolean) => void;
};

type CoreFieldKey =
  | "quantity"
  | "nominal"
  | "upper_tolerance"
  | "lower_tolerance"
  | "feature_kind"
  | "depth"
  | "through"
  | "thread_spec"
  | "thread_depth"
  | "radius_value"
  | "angle_value";

type CoreField = {
  key: CoreFieldKey;
  label: string;
  kind: "decimal" | "integer" | "text" | "boolean" | "feature_kind";
};

type AcknowledgedItemDraft = {
  draftSignature: string;
  persistedSignature: string;
  snapshotGeneration: number;
};

const QUANTITY_FIELD: CoreField = {
  key: "quantity",
  label: zhCN.review.fields.quantity,
  kind: "integer",
};

const CORE_FIELDS: Record<CandidateType, CoreField[]> = {
  linear_dimension: [
    QUANTITY_FIELD,
    { key: "nominal", label: zhCN.review.fields.nominal, kind: "decimal" },
    { key: "upper_tolerance", label: zhCN.review.fields.upperTolerance, kind: "decimal" },
    { key: "lower_tolerance", label: zhCN.review.fields.lowerTolerance, kind: "decimal" },
  ],
  diameter_dimension: [
    QUANTITY_FIELD,
    { key: "nominal", label: zhCN.review.fields.diameter, kind: "decimal" },
    { key: "feature_kind", label: zhCN.review.fields.featureKind, kind: "feature_kind" },
    { key: "depth", label: zhCN.review.fields.depth, kind: "decimal" },
    { key: "through", label: zhCN.review.fields.through, kind: "boolean" },
  ],
  thread: [
    QUANTITY_FIELD,
    { key: "thread_spec", label: zhCN.review.fields.threadSpec, kind: "text" },
    { key: "thread_depth", label: zhCN.review.fields.threadDepth, kind: "decimal" },
    { key: "through", label: zhCN.review.fields.through, kind: "boolean" },
  ],
  radius: [
    QUANTITY_FIELD,
    { key: "radius_value", label: zhCN.review.fields.radius, kind: "decimal" },
  ],
  angle: [
    QUANTITY_FIELD,
    { key: "angle_value", label: zhCN.review.fields.angle, kind: "decimal" },
    { key: "upper_tolerance", label: zhCN.review.fields.upperTolerance, kind: "decimal" },
    { key: "lower_tolerance", label: zhCN.review.fields.lowerTolerance, kind: "decimal" },
  ],
  general_requirement: [QUANTITY_FIELD],
  composite: [QUANTITY_FIELD],
};

function coreFieldsFor(itemType: unknown): CoreField[] {
  if (typeof itemType !== "string") return [];
  const fields = (CORE_FIELDS as Readonly<Record<string, CoreField[]>>)[itemType];
  return Array.isArray(fields) ? fields : [];
}

const CANDIDATE_TYPES: Array<{ value: CandidateType; label: string }> = [
  { value: "linear_dimension", label: zhCN.review.types.linear_dimension },
  { value: "diameter_dimension", label: zhCN.review.types.diameter_dimension },
  { value: "thread", label: zhCN.review.types.thread },
  { value: "radius", label: zhCN.review.types.radius },
  { value: "angle", label: zhCN.review.types.angle },
  { value: "general_requirement", label: zhCN.review.types.general_requirement },
  { value: "composite", label: zhCN.review.types.composite },
];

const COARSE_TYPES = [
  {
    value: "geometric_tolerance",
    label: zhCN.review.coarseTypes.geometric_tolerance,
  },
  { value: "roughness", label: zhCN.review.coarseTypes.roughness },
  { value: "weld", label: zhCN.review.coarseTypes.weld },
  {
    value: "cross_view_duplicate",
    label: zhCN.review.coarseTypes.cross_view_duplicate,
  },
] as const;

function parseCoordinates(value: string): PdfCoordinates | null {
  const coordinates = value.split(",").map((part) => Number(part.trim()));
  if (
    coordinates.length !== 4 ||
    coordinates.some((coordinate) => !Number.isFinite(coordinate))
  ) return null;
  return coordinates as PdfCoordinates;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function comparableText(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function parseCoreValue(
  field: CoreField,
  value: string,
): { valid: boolean; value: unknown } {
  const trimmed = value.trim();
  if (trimmed === "") return { valid: true, value: null };
  if (field.kind === "integer") {
    const parsed = Number(trimmed);
    return {
      valid: Number.isInteger(parsed) && parsed >= 1,
      value: parsed,
    };
  }
  if (field.kind === "boolean") {
    return {
      valid: trimmed === "true" || trimmed === "false",
      value: trimmed === "true",
    };
  }
  return { valid: true, value: trimmed };
}

function persistedItemSignature(item: ReviewItem): string {
  return JSON.stringify(
    item.coarse_type !== undefined
      ? [
          item.raw_text,
          item.coordinates?.join(",") ?? "",
          item.coarse_type,
          item.requires_confirmation ?? false,
        ]
      : [
          item.raw_text,
          ...coreFieldsFor(item.item_type).map(
            (field) => displayValue(item[field.key]),
          ),
        ],
  );
}

export function ReviewPanel({
  items,
  onCommand,
  disabled = false,
  selectedItemId,
  selectedItemPresentation,
  onSelectItem,
  pageIndex = 0,
  onDraftChange,
}: ReviewPanelProps) {
  const [rawTexts, setRawTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(items.map((item) => [item.item_id, item.raw_text])),
  );
  const [coreValues, setCoreValues] = useState<
    Record<string, Partial<Record<CoreFieldKey, string>>>
  >(() =>
    Object.fromEntries(
      items.map((item) => [
        item.item_id,
        Object.fromEntries(
          coreFieldsFor(item.item_type).map(
            (field) => [field.key, displayValue(item[field.key])],
          ),
        ),
      ]),
    ),
  );
  const [complexCoordinates, setComplexCoordinates] = useState<Record<string, string>>(
    () =>
      Object.fromEntries(
        items.map((item) => [item.item_id, item.coordinates?.join(",") ?? ""]),
      ),
  );
  const [coarseTypes, setCoarseTypes] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      items.map((item) => [item.item_id, item.coarse_type ?? "roughness"]),
    ),
  );
  const [confirmationFields, setConfirmationFields] = useState<Record<string, boolean>>(
    () =>
      Object.fromEntries(
        items.map((item) => [item.item_id, item.requires_confirmation ?? false]),
      ),
  );
  const [splitTexts, setSplitTexts] = useState<Record<string, string>>({});
  const [editingItemId, setEditingItemId] = useState<string>();
  const [acknowledgedItemDrafts, setAcknowledgedItemDrafts] = useState<
    Record<string, AcknowledgedItemDraft>
  >({});
  const [dirtySplitIds, setDirtySplitIds] = useState<string[]>([]);
  const [manualDraftDirty, setManualDraftDirty] = useState(false);
  const [manualRawText, setManualRawText] = useState("");
  const [manualCoordinates, setManualCoordinates] = useState("");
  const [manualScope, setManualScope] = useState<
    "local_feature" | "global_requirement"
  >("local_feature");
  const [manualType, setManualType] = useState<CandidateType>("thread");
  const [manualBalloonRequired, setManualBalloonRequired] = useState(true);
  const [pendingExcludeItemId, setPendingExcludeItemId] = useState<string>();
  const [excludeSubmitting, setExcludeSubmitting] = useState(false);
  const excludeButtonRef = useRef<HTMLButtonElement>(null);
  const cancelExcludeButtonRef = useRef<HTMLButtonElement>(null);
  const activeItems = useMemo(() => items.filter((item) => item.active), [items]);
  const latestItemsSnapshotRef = useRef({ items, generation: 0 });
  if (latestItemsSnapshotRef.current.items !== items) {
    latestItemsSnapshotRef.current = {
      items,
      generation: latestItemsSnapshotRef.current.generation + 1,
    };
  }
  const itemsSnapshotGeneration = latestItemsSnapshotRef.current.generation;
  const persistedSignaturesRef = useRef<Record<string, string>>(
    Object.fromEntries(items.map(
      (item) => [item.item_id, persistedItemSignature(item)],
    )),
  );
  const itemDraftSignature = (item: ReviewItem) => JSON.stringify(
    item.coarse_type !== undefined
      ? [
          rawTexts[item.item_id] ?? item.raw_text,
          complexCoordinates[item.item_id] ?? "",
          coarseTypes[item.item_id] ?? item.coarse_type,
          confirmationFields[item.item_id] ?? false,
        ]
      : [
          rawTexts[item.item_id] ?? item.raw_text,
          ...coreFieldsFor(item.item_type).map(
            (field) => coreValues[item.item_id]?.[field.key] ?? "",
          ),
        ],
  );
  const latestDraftSignaturesRef = useRef<Record<string, string>>({});
  latestDraftSignaturesRef.current = Object.fromEntries(
    activeItems.map((item) => [item.item_id, itemDraftSignature(item)]),
  );
  const syncItemDraftFromPersisted = (item: ReviewItem) => {
    setRawTexts((current) => ({
      ...current,
      [item.item_id]: item.raw_text,
    }));
    setCoreValues((current) => ({
      ...current,
      [item.item_id]: Object.fromEntries(
        coreFieldsFor(item.item_type).map(
          (field) => [field.key, displayValue(item[field.key])],
        ),
      ),
    }));
    setComplexCoordinates((current) => ({
      ...current,
      [item.item_id]: item.coordinates?.join(",") ?? "",
    }));
    setCoarseTypes((current) => ({
      ...current,
      [item.item_id]: item.coarse_type ?? "roughness",
    }));
    setConfirmationFields((current) => ({
      ...current,
      [item.item_id]: item.requires_confirmation ?? false,
    }));
  };
  const dirtyItemIds = useMemo(
    () => activeItems
      .filter(
        (item) =>
          itemDraftSignature(item)
            !== (
              acknowledgedItemDrafts[item.item_id]?.draftSignature
              ?? persistedItemSignature(item)
            ),
      )
      .map((item) => item.item_id),
    [
      acknowledgedItemDrafts,
      activeItems,
      coarseTypes,
      complexCoordinates,
      confirmationFields,
      coreValues,
      rawTexts,
    ],
  );
  const selectedItem = activeItems.find((item) => item.item_id === selectedItemId);
  const selectedCoreFields = selectedItem === undefined
    ? []
    : coreFieldsFor(selectedItem.item_type);
  const selectedRawText = selectedItem === undefined
    ? ""
    : rawTexts[selectedItem.item_id] ?? selectedItem.raw_text;
  const rawTextMatchesParsedField =
    selectedItem !== undefined
    && selectedCoreFields.some((field) => {
      if (field.key === "quantity") return false;
      const parsedValue =
        coreValues[selectedItem.item_id]?.[field.key]
        ?? displayValue(selectedItem[field.key]);
      return parsedValue.trim() !== ""
        && comparableText(parsedValue) === comparableText(selectedRawText);
    });
  const showRawTextReference =
    selectedItem !== undefined
    && (
      selectedItem.coarse_type !== undefined
      || selectedItem.requires_confirmation === true
      || !rawTextMatchesParsedField
    );
  const selectedItemHeading = zhCN.review.itemHeading(
    selectedItemPresentation?.displayNumber,
    selectedItemPresentation?.typeLabel ?? zhCN.workbench.unknown,
  );
  const selectedItemNumberLabel =
    selectedItemPresentation?.numberKind === "formal"
    && selectedItemPresentation.displayNumber !== undefined
      ? zhCN.review.formalBalloonNumber(
          selectedItemPresentation.displayNumber,
        )
      : selectedItemPresentation?.numberLabel ?? zhCN.workbench.unknown;
  const isEditingSelected =
    selectedItem !== undefined && editingItemId === selectedItem.item_id;
  const isSelectedItemDirty =
    selectedItem !== undefined && dirtyItemIds.includes(selectedItem.item_id);
  const beginEditingSelected = () => {
    if (!disabled && selectedItem !== undefined) {
      setEditingItemId(selectedItem.item_id);
    }
  };

  useEffect(() => {
    onDraftChange?.(
      dirtyItemIds.length > 0 || dirtySplitIds.length > 0 || manualDraftDirty,
    );
  }, [dirtyItemIds, dirtySplitIds, manualDraftDirty, onDraftChange]);

  useEffect(() => {
    setEditingItemId(undefined);
    setPendingExcludeItemId(undefined);
  }, [selectedItemId]);

  useEffect(() => {
    if (pendingExcludeItemId !== undefined) {
      cancelExcludeButtonRef.current?.focus();
    }
  }, [pendingExcludeItemId]);

  useEffect(() => {
    const nextPersistedSignatures = { ...persistedSignaturesRef.current };
    const acknowledgedIdsToRetire: string[] = [];
    for (const item of activeItems) {
      const itemId = item.item_id;
      const persistedSignature = persistedItemSignature(item);
      const previousPersistedSignature =
        persistedSignaturesRef.current[itemId];
      const acknowledgedDraft = acknowledgedItemDrafts[itemId];
      const draftSignature = itemDraftSignature(item);

      if (
        acknowledgedDraft !== undefined
        && (
          persistedSignature !== acknowledgedDraft.persistedSignature
          || itemsSnapshotGeneration > acknowledgedDraft.snapshotGeneration
        )
        && draftSignature === acknowledgedDraft.draftSignature
        && editingItemId !== itemId
      ) {
        syncItemDraftFromPersisted(item);
        acknowledgedIdsToRetire.push(itemId);
      } else if (
        acknowledgedDraft === undefined
        && previousPersistedSignature !== undefined
        && persistedSignature !== previousPersistedSignature
        && draftSignature === previousPersistedSignature
        && editingItemId !== itemId
      ) {
        syncItemDraftFromPersisted(item);
      }
      nextPersistedSignatures[itemId] = persistedSignature;
    }
    persistedSignaturesRef.current = nextPersistedSignatures;
    if (acknowledgedIdsToRetire.length > 0) {
      setAcknowledgedItemDrafts((current) => {
        const next = { ...current };
        for (const itemId of acknowledgedIdsToRetire) delete next[itemId];
        return next;
      });
    }
  }, [
    acknowledgedItemDrafts,
    activeItems,
    coarseTypes,
    complexCoordinates,
    confirmationFields,
    coreValues,
    editingItemId,
    itemsSnapshotGeneration,
    rawTexts,
  ]);

  const setCoreValue = (itemId: string, key: CoreFieldKey, value: string) => {
    setCoreValues((current) => ({
      ...current,
      [itemId]: { ...current[itemId], [key]: value },
    }));
  };

  const editItem = async (item: ReviewItem) => {
    const submittedSignature = itemDraftSignature(item);
    const preSubmitPersistedSignature = persistedItemSignature(item);
    const preSubmitSnapshotGeneration =
      latestItemsSnapshotRef.current.generation;
    const fields: Record<string, unknown> = {
      raw_text: rawTexts[item.item_id] ?? item.raw_text,
    };
    if (item.coarse_type !== undefined) {
      const coordinates = parseCoordinates(complexCoordinates[item.item_id] ?? "");
      if (coordinates === null) return;
      Object.assign(fields, {
        coordinates,
        coarse_type: coarseTypes[item.item_id] ?? item.coarse_type,
        requires_confirmation:
          confirmationFields[item.item_id] ?? item.requires_confirmation ?? false,
      });
    } else {
      for (const field of coreFieldsFor(item.item_type)) {
        const value = coreValues[item.item_id]?.[field.key] ?? "";
        if (value.trim() === "" && item[field.key] === undefined) continue;
        const parsed = parseCoreValue(field, value);
        if (!parsed.valid) return;
        fields[field.key] = parsed.value;
      }
    }
    const outcome = await onCommand({
      type: "edit",
      item_id: item.item_id,
      fields,
    });
    if (outcome === false) return;
    const latestItemsSnapshot = latestItemsSnapshotRef.current;
    const latestItem = latestItemsSnapshot.items.find(
      (candidate) => candidate.item_id === item.item_id,
    );
    const draftStillMatchesSubmission =
      latestDraftSignaturesRef.current[item.item_id] === submittedSignature;
    if (
      draftStillMatchesSubmission
      && latestItem !== undefined
      && (
        persistedItemSignature(latestItem) !== preSubmitPersistedSignature
        || latestItemsSnapshot.generation > preSubmitSnapshotGeneration
      )
    ) {
      syncItemDraftFromPersisted(latestItem);
      persistedSignaturesRef.current[item.item_id] =
        persistedItemSignature(latestItem);
      setAcknowledgedItemDrafts((current) => {
        if (current[item.item_id] === undefined) return current;
        const next = { ...current };
        delete next[item.item_id];
        return next;
      });
    } else {
      setAcknowledgedItemDrafts((current) => ({
        ...current,
        [item.item_id]: {
          draftSignature: submittedSignature,
          persistedSignature: preSubmitPersistedSignature,
          snapshotGeneration: preSubmitSnapshotGeneration,
        },
      }));
    }
    if (draftStillMatchesSubmission) {
      setEditingItemId((current) =>
        current === item.item_id ? undefined : current,
      );
    }
  };

  const resetManualItem = () => {
    setManualRawText("");
    setManualCoordinates("");
    setManualScope("local_feature");
    setManualType("thread");
    setManualBalloonRequired(true);
    setManualDraftDirty(false);
  };
  const addManualItem = async () => {
    const coordinates = parseCoordinates(manualCoordinates);
    if (manualRawText.trim() === "" || coordinates === null) return;
    const outcome = await onCommand({
      type: "add",
      raw_text: manualRawText,
      item_type: manualType,
      coordinates,
      scope: manualScope,
      balloon_required: manualBalloonRequired,
      page_index: pageIndex,
    });
    if (outcome === false) return;
    resetManualItem();
  };

  const splitItem = async (item: ReviewItem) => {
    const parts = (splitTexts[item.item_id] ?? "")
      .split("|")
      .map((rawText) => rawText.trim())
      .filter(Boolean)
      .map((raw_text) => ({ raw_text }));
    if (parts.length < 2) return;
    const outcome = await onCommand({
      type: "split",
      item_id: item.item_id,
      parts,
    });
    if (outcome === false) return;
    setSplitTexts((current) => ({
      ...current,
      [item.item_id]: "",
    }));
    setDirtySplitIds((current) =>
      current.filter((candidate) => candidate !== item.item_id),
    );
  };
  const cancelExclude = () => {
    if (excludeSubmitting) return;
    setPendingExcludeItemId(undefined);
    excludeButtonRef.current?.focus();
  };
  const confirmExclude = async (item: ReviewItem) => {
    if (excludeSubmitting) return;
    setExcludeSubmitting(true);
    try {
      const outcome = await onCommand({
        type: "exclude",
        item_id: item.item_id,
      });
      if (outcome !== false) {
        setPendingExcludeItemId(undefined);
        excludeButtonRef.current?.focus();
      }
    } finally {
      setExcludeSubmitting(false);
    }
  };

  return (
    <section className="review-panel" aria-label={zhCN.review.region}>
      <h2>{zhCN.review.title}</h2>
      {selectedItem === undefined ? (
        <p className="review-select-hint">{zhCN.review.selectItemHint}</p>
      ) : (
        <article
          aria-label={selectedItemHeading}
          className="review-selected-item"
          data-selected="true"
          onClick={() => onSelectItem?.(selectedItem.item_id)}
        >
          <header className="review-selected-item__header">
            <div>
              <h3>{selectedItemHeading}</h3>
              <p>
                <span>{selectedItemNumberLabel}</span>
                <span>
                  {selectedItemPresentation?.pageLabel
                    ?? zhCN.workbench.unknown}
                </span>
              </p>
            </div>
            {selectedItemPresentation === undefined ? null : (
              <span
                className={`geometry-state geometry-state--${
                  selectedItemPresentation.status
                }`}
              >
                {selectedItemPresentation.statusLabel}
              </span>
            )}
          </header>
          <div className="review-selected-item__workspace">
          <div className="review-selected-item__form">
          {showRawTextReference ? (
          <fieldset
            className="review-field-group review-field-group--source"
            disabled={disabled}
          >
            <legend>{zhCN.review.drawingSource}</legend>
            <div className="review-field-reference">
              <span>{zhCN.review.recognizedText}</span>
              <p
                role="note"
                aria-label={zhCN.review.fieldForItem(
                  zhCN.review.recognizedText,
                  selectedRawText,
                )}
              >
                {selectedRawText}
              </p>
            </div>
            {selectedItem.coarse_type === undefined ? null : (
              <>
                <label>
                  {zhCN.review.coordinates}
                  <input
                    aria-label={zhCN.review.fieldForItem(
                      zhCN.review.coordinates,
                      selectedItem.raw_text,
                    )}
                    disabled={disabled}
                    readOnly={!isEditingSelected}
                    value={complexCoordinates[selectedItem.item_id] ?? ""}
                    onFocus={beginEditingSelected}
                    onChange={(event) => {
                      setComplexCoordinates((current) => ({
                        ...current,
                        [selectedItem.item_id]: event.target.value,
                      }));
                    }}
                  />
                </label>
                <label>
                  {zhCN.review.coarseType}
                  <select
                    aria-label={zhCN.review.fieldForItem(
                      zhCN.review.coarseType,
                      selectedItem.raw_text,
                    )}
                    disabled={disabled || !isEditingSelected}
                    value={
                      coarseTypes[selectedItem.item_id]
                      ?? selectedItem.coarse_type
                    }
                    onChange={(event) => {
                      setCoarseTypes((current) => ({
                        ...current,
                        [selectedItem.item_id]: event.target.value,
                      }));
                    }}
                  >
                    {COARSE_TYPES.some(
                      ({ value }) =>
                        value
                        === (coarseTypes[selectedItem.item_id]
                          ?? selectedItem.coarse_type),
                    ) ? null : (
                      <option
                        value={
                          coarseTypes[selectedItem.item_id]
                          ?? selectedItem.coarse_type
                        }
                      >
                        {zhCN.workbench.unknown}
                      </option>
                    )}
                    {COARSE_TYPES.map(({ value, label }) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="review-field-group__confirmation">
                  <input
                    type="checkbox"
                    aria-label={zhCN.review.fieldForItem(
                      zhCN.review.requiresConfirmation,
                      selectedItem.raw_text,
                    )}
                    disabled={disabled || !isEditingSelected}
                    checked={confirmationFields[selectedItem.item_id] ?? false}
                    onChange={(event) => {
                      setConfirmationFields((current) => ({
                        ...current,
                        [selectedItem.item_id]: event.target.checked,
                      }));
                    }}
                  />
                  {zhCN.review.requiresConfirmation}
                </label>
              </>
            )}
          </fieldset>
          ) : null}
          {selectedCoreFields.length === 0 ? null : (
            <fieldset
              className="review-field-group review-field-group--parsed"
              disabled={disabled}
            >
              <legend>{zhCN.review.parsedResult}</legend>
              {selectedCoreFields.map((field) => (
                <label key={field.key}>
                  {field.label}
                  {field.kind === "boolean" ? (
                    <select
                      aria-label={zhCN.review.fieldForItem(
                        field.label,
                        selectedItem.raw_text,
                      )}
                      disabled={disabled || !isEditingSelected}
                      value={coreValues[selectedItem.item_id]?.[field.key] ?? ""}
                      onChange={(event) =>
                        setCoreValue(
                          selectedItem.item_id,
                          field.key,
                          event.target.value,
                        )
                      }
                    >
                      <option value="">{zhCN.review.unspecified}</option>
                      <option value="true">{zhCN.review.yes}</option>
                      <option value="false">{zhCN.review.no}</option>
                    </select>
                  ) : field.kind === "feature_kind" ? (
                    <select
                      aria-label={zhCN.review.fieldForItem(
                        field.label,
                        selectedItem.raw_text,
                      )}
                      disabled={disabled || !isEditingSelected}
                      value={coreValues[selectedItem.item_id]?.[field.key] ?? ""}
                      onChange={(event) =>
                        setCoreValue(
                          selectedItem.item_id,
                          field.key,
                          event.target.value,
                        )
                      }
                    >
                      <option value="">{zhCN.review.unspecified}</option>
                      <option value="hole">{zhCN.review.featureKinds.hole}</option>
                      <option value="shaft">{zhCN.review.featureKinds.shaft}</option>
                      <option value="cylindrical_feature">{zhCN.review.featureKinds.cylindrical_feature}</option>
                      <option value="unknown">{zhCN.review.featureKinds.unknown}</option>
                    </select>
                  ) : (
                    <input
                      aria-label={zhCN.review.fieldForItem(
                        field.label,
                        selectedItem.raw_text,
                      )}
                      disabled={disabled}
                      readOnly={!isEditingSelected}
                      inputMode={field.kind === "decimal" ? "decimal" : undefined}
                      type={field.kind === "integer" ? "number" : "text"}
                      min={field.kind === "integer" ? 1 : undefined}
                      step={field.kind === "integer" ? 1 : undefined}
                      value={coreValues[selectedItem.item_id]?.[field.key] ?? ""}
                      onFocus={beginEditingSelected}
                      onChange={(event) =>
                        setCoreValue(
                          selectedItem.item_id,
                          field.key,
                          event.target.value,
                        )
                      }
                    />
                  )}
                </label>
              ))}
            </fieldset>
          )}
          </div>
          <aside
            className="review-command-rail review-command-rail--flat"
            aria-label="检验项操作"
          >
            <fieldset className="review-command-rail__group">
              <legend>{zhCN.review.decisionGroup}</legend>
              <button
                type="button"
                className="review-command-rail__secondary"
                aria-label={zhCN.review.actionForItem(
                  zhCN.review.keep,
                  selectedItem.raw_text,
                )}
                disabled={disabled}
                onClick={() =>
                  onCommand({ type: "keep", item_id: selectedItem.item_id })
                }
              >
                {zhCN.review.keep}
              </button>
              <button
                ref={excludeButtonRef}
                type="button"
                className="review-command-rail__secondary review-command-rail__danger"
                aria-label={zhCN.review.actionForItem(
                  zhCN.review.exclude,
                  selectedItem.raw_text,
                )}
                disabled={disabled || excludeSubmitting}
                onClick={() => setPendingExcludeItemId(selectedItem.item_id)}
              >
                {zhCN.review.exclude}
              </button>
              <p className="review-command-rail__helper">
                {zhCN.review.excludeHelp}
              </p>
              {pendingExcludeItemId === selectedItem.item_id && (
                <div
                  className="review-command-rail__confirmation"
                  role="alertdialog"
                  aria-labelledby="exclude-confirmation-title"
                  aria-describedby="exclude-confirmation-description"
                  onKeyDown={(event) => {
                    if (event.key === "Escape") cancelExclude();
                  }}
                >
                  <strong id="exclude-confirmation-title">
                    {zhCN.review.excludeConfirmTitle}
                  </strong>
                  <p id="exclude-confirmation-description">
                    {zhCN.review.excludeConfirmDescription}
                  </p>
                  <div className="review-command-rail__confirmation-actions">
                    <button
                      ref={cancelExcludeButtonRef}
                      type="button"
                      className="review-command-rail__secondary"
                      aria-label={zhCN.review.cancelExclude}
                      disabled={disabled || excludeSubmitting}
                      onClick={cancelExclude}
                    >
                      {zhCN.review.cancelExclude}
                    </button>
                    <button
                      type="button"
                      className="review-command-rail__confirm-danger"
                      aria-label={zhCN.review.confirmExclude}
                      disabled={disabled || excludeSubmitting}
                      onClick={() => confirmExclude(selectedItem)}
                    >
                      {zhCN.review.confirmExclude}
                    </button>
                  </div>
                </div>
              )}
            </fieldset>
            <fieldset className="review-command-rail__group">
              <legend>{zhCN.review.contentGroup}</legend>
              <button
                type="button"
                className="review-command-rail__primary"
                aria-label={zhCN.review.actionForItem(
                  zhCN.review.edit,
                  selectedItem.raw_text,
                )}
                disabled={disabled || isEditingSelected}
                onClick={beginEditingSelected}
              >
                {zhCN.review.edit}
              </button>
              <button
                type="button"
                className="review-command-rail__primary"
                aria-label={zhCN.review.actionForItem(
                  zhCN.review.saveEdit,
                  selectedItem.raw_text,
                )}
                disabled={
                  disabled
                  || !isEditingSelected
                  || !isSelectedItemDirty
                }
                onClick={() => editItem(selectedItem)}
              >
                {zhCN.review.saveEdit}
              </button>
              <button
                type="button"
                className="review-command-rail__secondary"
                aria-label={zhCN.review.fieldForItem(
                  zhCN.review.accept,
                  selectedItem.raw_text,
                )}
                disabled={disabled || !selectedItem.requires_confirmation}
                onClick={() =>
                  onCommand({
                    type: "resolve_confirmation",
                    item_id: selectedItem.item_id,
                    accepted: true,
                  })
                }
              >
                {zhCN.review.accept}
              </button>
              <button
                type="button"
                className="review-command-rail__secondary"
                aria-label={zhCN.review.fieldForItem(
                  zhCN.review.reject,
                  selectedItem.raw_text,
                )}
                disabled={disabled || !selectedItem.requires_confirmation}
                onClick={() =>
                  onCommand({
                    type: "resolve_confirmation",
                    item_id: selectedItem.item_id,
                    accepted: false,
                  })
                }
              >
                {zhCN.review.reject}
              </button>
            </fieldset>
            <fieldset className="review-command-rail__group">
              <legend>{zhCN.review.balloonGroup}</legend>
              <button
                type="button"
                className="review-command-rail__secondary"
                aria-label={zhCN.review.fieldForItem(
                  zhCN.review.requireBalloon,
                  selectedItem.raw_text,
                )}
                disabled={disabled || selectedItem.balloon_required === true}
                onClick={() =>
                  onCommand({
                    type: "set_balloon_required",
                    item_id: selectedItem.item_id,
                    balloon_required: true,
                  })
                }
              >
                {zhCN.review.requireBalloon}
              </button>
              <button
                type="button"
                className="review-command-rail__secondary"
                aria-label={zhCN.review.fieldForItem(
                  zhCN.review.noBalloon,
                  selectedItem.raw_text,
                )}
                disabled={disabled || selectedItem.balloon_required === false}
                onClick={() =>
                  onCommand({
                    type: "set_balloon_required",
                    item_id: selectedItem.item_id,
                    balloon_required: false,
                  })
                }
              >
                {zhCN.review.noBalloon}
              </button>
              <p className="review-command-rail__helper">
                {zhCN.review.noBalloonHelp}
              </p>
            </fieldset>
          </aside>
          </div>
          <div className="review-split-row">
          <label>
            {zhCN.review.splitParts}
            <input
              aria-label={zhCN.review.fieldForItem(
                zhCN.review.splitParts,
                selectedItem.raw_text,
              )}
              value={splitTexts[selectedItem.item_id] ?? ""}
              placeholder={zhCN.review.splitPlaceholder}
              disabled={disabled}
              onChange={(event) => {
                const value = event.target.value;
                setSplitTexts((current) => ({
                  ...current,
                  [selectedItem.item_id]: value,
                }));
                setDirtySplitIds((current) => value === ""
                  ? current.filter((candidate) => candidate !== selectedItem.item_id)
                  : current.includes(selectedItem.item_id)
                    ? current
                    : [...current, selectedItem.item_id]);
              }}
            />
          </label>
          <button
            type="button"
            aria-label={zhCN.review.actionForItem(
              zhCN.review.split,
              selectedItem.raw_text,
            )}
            disabled={disabled || selectedItem.item_type === undefined}
            onClick={() => splitItem(selectedItem)}
          >
            {zhCN.review.split}
          </button>
          </div>
        </article>
      )}
      <fieldset className="review-manual-item" disabled={disabled}>
        <legend>{zhCN.review.manualItem}</legend>
        <label>
          {zhCN.review.rawText}
          <input
            aria-label={zhCN.review.manualRawText}
            value={manualRawText}
            onChange={(event) => {
              setManualRawText(event.target.value);
              setManualDraftDirty(true);
            }}
          />
        </label>
        <label>
          {zhCN.review.coordinates}
          <input
            aria-label={zhCN.review.manualCoordinates}
            value={manualCoordinates}
            placeholder={zhCN.review.manualCoordinatesPlaceholder}
            onChange={(event) => {
              setManualCoordinates(event.target.value);
              setManualDraftDirty(true);
            }}
          />
        </label>
        <label>
          {zhCN.review.scope}
          <select
            aria-label={zhCN.review.manualScope}
            value={manualScope}
            onChange={(event) => {
              setManualScope(
                event.target.value as "local_feature" | "global_requirement",
              );
              setManualDraftDirty(true);
            }}
          >
            <option value="local_feature">{zhCN.review.localFeature}</option>
            <option value="global_requirement">{zhCN.review.globalRequirement}</option>
          </select>
        </label>
        <label>
          {zhCN.review.type}
          <select
            aria-label={zhCN.review.manualType}
            value={manualType}
            onChange={(event) => {
              setManualType(event.target.value as CandidateType);
              setManualDraftDirty(true);
            }}
          >
            {CANDIDATE_TYPES.map((candidateType) => (
              <option key={candidateType.value} value={candidateType.value}>
                {candidateType.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            aria-label={zhCN.review.manualBalloonRequired}
            checked={manualBalloonRequired}
            onChange={(event) => {
              setManualBalloonRequired(event.target.checked);
              setManualDraftDirty(true);
            }}
          />
          {zhCN.review.balloonRequired}
        </label>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button
            type="button"
            aria-label={zhCN.review.addItem}
            disabled={disabled}
            onClick={addManualItem}
          >
            {zhCN.review.addItem}
          </button>
          <button
            type="button"
            aria-label={zhCN.review.cancelManualItem}
            disabled={disabled || !manualDraftDirty}
            onClick={resetManualItem}
          >
            {zhCN.review.cancelManualItem}
          </button>
        </div>
      </fieldset>
    </section>
  );
}
