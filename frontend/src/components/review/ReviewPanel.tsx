import { useMemo, useState } from "react";

import type {
  CandidateType,
  PdfCoordinates,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";


type ReviewPanelProps = {
  items: ReviewItem[];
  onCommand: (command: ReviewCommand) => void;
  disabled?: boolean;
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
  label: "Quantity",
  kind: "integer",
};

const CORE_FIELDS: Record<CandidateType, CoreField[]> = {
  linear_dimension: [
    QUANTITY_FIELD,
    { key: "nominal", label: "Nominal", kind: "decimal" },
    { key: "upper_tolerance", label: "Upper tolerance", kind: "decimal" },
    { key: "lower_tolerance", label: "Lower tolerance", kind: "decimal" },
  ],
  diameter_dimension: [
    QUANTITY_FIELD,
    { key: "nominal", label: "Diameter", kind: "decimal" },
    { key: "feature_kind", label: "Feature kind", kind: "feature_kind" },
    { key: "depth", label: "Depth", kind: "decimal" },
    { key: "through", label: "Through", kind: "boolean" },
  ],
  thread: [
    QUANTITY_FIELD,
    { key: "thread_spec", label: "Thread specification", kind: "text" },
    { key: "thread_depth", label: "Thread depth", kind: "decimal" },
    { key: "through", label: "Through", kind: "boolean" },
  ],
  radius: [
    QUANTITY_FIELD,
    { key: "radius_value", label: "Radius", kind: "decimal" },
  ],
  angle: [
    QUANTITY_FIELD,
    { key: "angle_value", label: "Angle", kind: "decimal" },
    { key: "upper_tolerance", label: "Upper tolerance", kind: "decimal" },
    { key: "lower_tolerance", label: "Lower tolerance", kind: "decimal" },
  ],
  general_requirement: [QUANTITY_FIELD],
  composite: [QUANTITY_FIELD],
};

const CANDIDATE_TYPES: Array<{ value: CandidateType; label: string }> = [
  { value: "linear_dimension", label: "Linear dimension" },
  { value: "diameter_dimension", label: "Diameter dimension" },
  { value: "thread", label: "Thread" },
  { value: "radius", label: "Radius" },
  { value: "angle", label: "Angle" },
  { value: "general_requirement", label: "General requirement" },
  { value: "composite", label: "Composite" },
];

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
          (item.item_type === undefined ? [] : CORE_FIELDS[item.item_type]).map(
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
  const [manualRawText, setManualRawText] = useState("");
  const [manualCoordinates, setManualCoordinates] = useState("");
  const [manualScope, setManualScope] = useState<
    "local_feature" | "global_requirement"
  >("local_feature");
  const [manualType, setManualType] = useState<CandidateType>("thread");
  const [manualBalloonRequired, setManualBalloonRequired] = useState(true);
  const activeItems = useMemo(() => items.filter((item) => item.active), [items]);

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

  const editItem = (item: ReviewItem) => {
    const fields: Record<string, unknown> = {
      raw_text: rawTexts[item.item_id] ?? item.raw_text,
    };
    if (item.coarse_type !== undefined) {
      const coordinates = parseCoordinates(complexCoordinates[item.item_id] ?? "");
      if (coordinates === null) return;
      onCommand({
        type: "edit",
        item_id: item.item_id,
        fields: {
          ...fields,
          coordinates,
          coarse_type: coarseTypes[item.item_id] ?? item.coarse_type,
          requires_confirmation:
            confirmationFields[item.item_id] ?? item.requires_confirmation ?? false,
        },
      });
      return;
    }
    for (const field of item.item_type === undefined ? [] : CORE_FIELDS[item.item_type]) {
      const value = coreValues[item.item_id]?.[field.key] ?? "";
      if (value.trim() === "" && item[field.key] === undefined) continue;
      const parsed = parseCoreValue(field, value);
      if (!parsed.valid) return;
      fields[field.key] = parsed.value;
    }
    onCommand({ type: "edit", item_id: item.item_id, fields });
  };

  const addManualItem = () => {
    const coordinates = parseCoordinates(manualCoordinates);
    if (manualRawText.trim() === "" || coordinates === null) return;
    onCommand({
      type: "add",
      raw_text: manualRawText,
      item_type: manualType,
      coordinates,
      scope: manualScope,
      balloon_required: manualBalloonRequired,
    });
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
    <section aria-label="Review commands">
      <h2>Inspection items</h2>
      {activeItems.map((item) => (
        <article
          key={item.item_id}
          style={{ borderBottom: "1px solid #e5e7eb", padding: 8 }}
        >
          <label>
            <input
              type="checkbox"
              aria-label={`Select ${item.item_id}`}
              checked={selectedIds.includes(item.item_id)}
              onChange={() => toggleSelected(item.item_id)}
            />
            {item.item_id}
          </label>
          <label style={{ display: "block" }}>
            Raw text {item.item_id}
            <input
              aria-label={`Raw text ${item.item_id}`}
              value={rawTexts[item.item_id] ?? item.raw_text}
              onChange={(event) =>
                setRawTexts((current) => ({
                  ...current,
                  [item.item_id]: event.target.value,
                }))
              }
            />
          </label>
          {item.item_type === undefined
            ? null
            : CORE_FIELDS[item.item_type].map((field) => (
                <label key={field.key} style={{ display: "block" }}>
                  {field.label} {item.item_id}
                  {field.kind === "boolean" ? (
                    <select
                      aria-label={`${field.label} ${item.item_id}`}
                      value={coreValues[item.item_id]?.[field.key] ?? ""}
                      onChange={(event) =>
                        setCoreValue(item.item_id, field.key, event.target.value)
                      }
                    >
                      <option value="">Unspecified</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : field.kind === "feature_kind" ? (
                    <select
                      aria-label={`${field.label} ${item.item_id}`}
                      value={coreValues[item.item_id]?.[field.key] ?? ""}
                      onChange={(event) =>
                        setCoreValue(item.item_id, field.key, event.target.value)
                      }
                    >
                      <option value="">Unspecified</option>
                      <option value="hole">Hole</option>
                      <option value="shaft">Shaft</option>
                      <option value="cylindrical_feature">Cylindrical feature</option>
                      <option value="unknown">Unknown</option>
                    </select>
                  ) : (
                    <input
                      aria-label={`${field.label} ${item.item_id}`}
                      inputMode={field.kind === "decimal" ? "decimal" : undefined}
                      type={field.kind === "integer" ? "number" : "text"}
                      min={field.kind === "integer" ? 1 : undefined}
                      step={field.kind === "integer" ? 1 : undefined}
                      value={coreValues[item.item_id]?.[field.key] ?? ""}
                      onChange={(event) =>
                        setCoreValue(item.item_id, field.key, event.target.value)
                      }
                    />
                  )}
                </label>
              ))}
          {item.coarse_type === undefined ? null : (
            <fieldset>
              <legend>Complex item fields</legend>
              <label>
                Coordinates {item.item_id}
                <input
                  aria-label={`Coordinates ${item.item_id}`}
                  value={complexCoordinates[item.item_id] ?? ""}
                  onChange={(event) =>
                    setComplexCoordinates((current) => ({
                      ...current,
                      [item.item_id]: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Coarse type {item.item_id}
                <select
                  aria-label={`Coarse type ${item.item_id}`}
                  value={coarseTypes[item.item_id] ?? item.coarse_type}
                  onChange={(event) =>
                    setCoarseTypes((current) => ({
                      ...current,
                      [item.item_id]: event.target.value,
                    }))
                  }
                >
                  <option value="geometric_tolerance">Geometric tolerance</option>
                  <option value="roughness">Roughness</option>
                  <option value="weld">Weld</option>
                  <option value="cross_view_duplicate">Cross-view duplicate</option>
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  aria-label={`Requires confirmation field ${item.item_id}`}
                  checked={confirmationFields[item.item_id] ?? false}
                  onChange={(event) =>
                    setConfirmationFields((current) => ({
                      ...current,
                      [item.item_id]: event.target.checked,
                    }))
                  }
                />
                Requires confirmation
              </label>
            </fieldset>
          )}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              type="button"
              aria-label={`Keep ${item.item_id}`}
              disabled={disabled}
              onClick={() => onCommand({ type: "keep", item_id: item.item_id })}
            >
              Keep
            </button>
            <button
              type="button"
              aria-label={`Exclude ${item.item_id}`}
              disabled={disabled}
              onClick={() => onCommand({ type: "exclude", item_id: item.item_id })}
            >
              Exclude
            </button>
            <button
              type="button"
              aria-label={`Edit ${item.item_id}`}
              disabled={disabled}
              onClick={() => editItem(item)}
            >
              Edit
            </button>
            <button
              type="button"
              aria-label={`Accept confirmation ${item.item_id}`}
              disabled={disabled || !item.requires_confirmation}
              onClick={() =>
                onCommand({
                  type: "resolve_confirmation",
                  item_id: item.item_id,
                  accepted: true,
                })
              }
            >
              Accept
            </button>
            <button
              type="button"
              aria-label={`Reject confirmation ${item.item_id}`}
              disabled={disabled || !item.requires_confirmation}
              onClick={() =>
                onCommand({
                  type: "resolve_confirmation",
                  item_id: item.item_id,
                  accepted: false,
                })
              }
            >
              Reject
            </button>
            <button
              type="button"
              aria-label={`Require balloon ${item.item_id}`}
              disabled={disabled || item.balloon_required === true}
              onClick={() =>
                onCommand({
                  type: "set_balloon_required",
                  item_id: item.item_id,
                  balloon_required: true,
                })
              }
            >
              Require balloon
            </button>
            <button
              type="button"
              aria-label={`Set balloon not required ${item.item_id}`}
              disabled={disabled || item.balloon_required === false}
              onClick={() =>
                onCommand({
                  type: "set_balloon_required",
                  item_id: item.item_id,
                  balloon_required: false,
                })
              }
            >
              No balloon
            </button>
          </div>
          <label style={{ display: "block" }}>
            Split parts {item.item_id}
            <input
              aria-label={`Split parts ${item.item_id}`}
              value={splitTexts[item.item_id] ?? ""}
              placeholder="part one|part two"
              onChange={(event) =>
                setSplitTexts((current) => ({
                  ...current,
                  [item.item_id]: event.target.value,
                }))
              }
            />
          </label>
          <button
            type="button"
            aria-label={`Split ${item.item_id}`}
            disabled={disabled || item.item_type === undefined}
            onClick={() => {
              const parts = (splitTexts[item.item_id] ?? "")
                .split("|")
                .map((rawText) => rawText.trim())
                .filter(Boolean)
                .map((raw_text) => ({ raw_text }));
              if (parts.length >= 2) {
                onCommand({ type: "split", item_id: item.item_id, parts });
              }
            }}
          >
            Split
          </button>
        </article>
      ))}
      <button
        type="button"
        aria-label="Merge selected"
        disabled={disabled}
        onClick={mergeSelected}
      >
        Merge selected
      </button>
      <fieldset>
        <legend>Manual item</legend>
        <label>
          Raw text
          <input
            aria-label="Manual raw text"
            value={manualRawText}
            onChange={(event) => setManualRawText(event.target.value)}
          />
        </label>
        <label>
          Coordinates
          <input
            aria-label="Manual coordinates"
            value={manualCoordinates}
            placeholder="x1,y1,x2,y2"
            onChange={(event) => setManualCoordinates(event.target.value)}
          />
        </label>
        <label>
          Scope
          <select
            aria-label="Manual scope"
            value={manualScope}
            onChange={(event) =>
              setManualScope(
                event.target.value as "local_feature" | "global_requirement",
              )
            }
          >
            <option value="local_feature">Local feature</option>
            <option value="global_requirement">Global requirement</option>
          </select>
        </label>
        <label>
          Type
          <select
            aria-label="Manual item type"
            value={manualType}
            onChange={(event) => setManualType(event.target.value as CandidateType)}
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
            aria-label="Manual balloon required"
            checked={manualBalloonRequired}
            onChange={(event) => setManualBalloonRequired(event.target.checked)}
          />
          Balloon required
        </label>
        <button
          type="button"
          aria-label="Add item"
          disabled={disabled}
          onClick={addManualItem}
        >
          Add item
        </button>
      </fieldset>
    </section>
  );
}
