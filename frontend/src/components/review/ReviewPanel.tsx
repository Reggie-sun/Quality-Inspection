import { useEffect, useMemo, useState } from "react";

import type {
  CandidateType,
  PdfCoordinates,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";


type ReviewPanelProps = {
  items: ReviewItem[];
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  disabled?: boolean;
  selectedItemId?: string;
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

export function ReviewPanel({
  items,
  onCommand,
  disabled = false,
  selectedItemId,
  onSelectItem,
  pageIndex = 0,
  onDraftChange,
}: ReviewPanelProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
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
  const [dirtySplitIds, setDirtySplitIds] = useState<string[]>([]);
  const [manualDraftDirty, setManualDraftDirty] = useState(false);
  const [manualRawText, setManualRawText] = useState("");
  const [manualCoordinates, setManualCoordinates] = useState("");
  const [manualScope, setManualScope] = useState<
    "local_feature" | "global_requirement"
  >("local_feature");
  const [manualType, setManualType] = useState<CandidateType>("thread");
  const [manualBalloonRequired, setManualBalloonRequired] = useState(true);
  const activeItems = useMemo(() => items.filter((item) => item.active), [items]);
  const dirtyItemIds = useMemo(
    () => activeItems
      .filter((item) => {
        if ((rawTexts[item.item_id] ?? item.raw_text) !== item.raw_text) {
          return true;
        }
        if (item.coarse_type !== undefined) {
          return (
            (complexCoordinates[item.item_id] ?? "")
              !== (item.coordinates?.join(",") ?? "")
            || (coarseTypes[item.item_id] ?? item.coarse_type)
              !== item.coarse_type
            || (confirmationFields[item.item_id] ?? false)
              !== (item.requires_confirmation ?? false)
          );
        }
        return coreFieldsFor(item.item_type).some(
          (field) =>
            (coreValues[item.item_id]?.[field.key] ?? "")
              !== displayValue(item[field.key]),
        );
      })
      .map((item) => item.item_id),
    [
      activeItems,
      coarseTypes,
      complexCoordinates,
      confirmationFields,
      coreValues,
      rawTexts,
    ],
  );
  const selectedItem = activeItems.find((item) => item.item_id === selectedItemId);
  const isEditingSelected =
    selectedItem !== undefined && editingItemId === selectedItem.item_id;
  const isSelectedItemDirty =
    selectedItem !== undefined && dirtyItemIds.includes(selectedItem.item_id);

  useEffect(() => {
    onDraftChange?.(
      dirtyItemIds.length > 0 || dirtySplitIds.length > 0 || manualDraftDirty,
    );
  }, [dirtyItemIds, dirtySplitIds, manualDraftDirty, onDraftChange]);

  useEffect(() => {
    setEditingItemId(undefined);
  }, [selectedItemId]);

  const toggleSelected = (itemId: string) => {
    setSelectedIds((current) =>
      current.includes(itemId)
        ? current.filter((candidate) => candidate !== itemId)
        : [...current, itemId],
    );
  };

  const setCoreValue = (itemId: string, key: CoreFieldKey, value: string) => {
    setCoreValues((current) => ({
      ...current,
      [itemId]: { ...current[itemId], [key]: value },
    }));
  };

  const editItem = async (item: ReviewItem) => {
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
    setEditingItemId((current) =>
      current === item.item_id ? undefined : current,
    );
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

  const mergeSelected = () => {
    const selected = activeItems.filter((item) => selectedIds.includes(item.item_id));
    if (selected.length < 2) return;
    onCommand({
      type: "merge",
      item_ids: selected.map((item) => item.item_id),
      raw_text: selected.map((item) => item.raw_text).join(" "),
    });
  };

  return (
    <section className="review-panel" aria-label={zhCN.review.region}>
      <h2>{zhCN.review.title}</h2>
      <details className="review-merge-selector">
        <summary>{zhCN.review.mergeSelection}</summary>
        <div className="review-merge-selector__items">
          {activeItems.map((item, index) => (
            <label key={item.item_id}>
              <input
                type="checkbox"
                aria-label={zhCN.review.selectItem(index + 1, item.raw_text)}
                checked={selectedIds.includes(item.item_id)}
                onChange={() => toggleSelected(item.item_id)}
              />
              <span>{item.raw_text}</span>
            </label>
          ))}
        </div>
        <button
          type="button"
          aria-label={zhCN.review.merge}
          disabled={disabled}
          onClick={mergeSelected}
        >
          {zhCN.review.merge}
        </button>
      </details>
      {selectedItem === undefined ? (
        <p className="review-select-hint">{zhCN.review.selectItemHint}</p>
      ) : (
        <article
          aria-label={selectedItem.raw_text}
          className="review-selected-item"
          data-selected="true"
          onClick={() => onSelectItem?.(selectedItem.item_id)}
        >
          <h3>{selectedItem.raw_text}</h3>
          <div className="review-selected-item__workspace">
          <div className="review-selected-item__form">
          <label>
            {zhCN.review.rawText}
            <input
              aria-label={zhCN.review.fieldForItem(
                zhCN.review.rawText,
                selectedItem.raw_text,
              )}
              disabled={disabled || !isEditingSelected}
              value={rawTexts[selectedItem.item_id] ?? selectedItem.raw_text}
              onChange={(event) => {
                setRawTexts((current) => ({
                  ...current,
                  [selectedItem.item_id]: event.target.value,
                }));
              }}
            />
          </label>
          {coreFieldsFor(selectedItem.item_type).map((field) => (
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
                      disabled={disabled || !isEditingSelected}
                      inputMode={field.kind === "decimal" ? "decimal" : undefined}
                      type={field.kind === "integer" ? "number" : "text"}
                      min={field.kind === "integer" ? 1 : undefined}
                      step={field.kind === "integer" ? 1 : undefined}
                      value={coreValues[selectedItem.item_id]?.[field.key] ?? ""}
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
          {selectedItem.coarse_type === undefined ? null : (
            <fieldset disabled={disabled || !isEditingSelected}>
              <legend>{zhCN.review.complexFields}</legend>
              <label>
                {zhCN.review.coordinates}
                <input
                  aria-label={zhCN.review.fieldForItem(
                    zhCN.review.coordinates,
                    selectedItem.raw_text,
                  )}
                  value={complexCoordinates[selectedItem.item_id] ?? ""}
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
                  value={
                    coarseTypes[selectedItem.item_id] ?? selectedItem.coarse_type
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
              <label>
                <input
                  type="checkbox"
                  aria-label={zhCN.review.fieldForItem(
                    zhCN.review.requiresConfirmation,
                    selectedItem.raw_text,
                  )}
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
            </fieldset>
          )}
          </div>
          <aside className="review-command-rail" aria-label="检验项操作">
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
              type="button"
              className="review-command-rail__secondary"
              aria-label={zhCN.review.actionForItem(
                zhCN.review.exclude,
                selectedItem.raw_text,
              )}
              disabled={disabled}
              onClick={() =>
                onCommand({ type: "exclude", item_id: selectedItem.item_id })
              }
            >
              {zhCN.review.exclude}
            </button>
            <button
              type="button"
              className="review-command-rail__primary"
              aria-label={zhCN.review.actionForItem(
                zhCN.review.edit,
                selectedItem.raw_text,
              )}
              disabled={disabled || isEditingSelected}
              onClick={() => setEditingItemId(selectedItem.item_id)}
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
