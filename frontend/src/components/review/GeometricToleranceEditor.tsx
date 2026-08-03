import { useState } from "react";

import type {
  EditGeometricTolerance,
  GeometricToleranceReviewItem,
  GeometricToleranceType,
  GdtDatumReference,
  GdtFrame,
  GdtModifier,
  GdtSegment,
  ReviewCommand,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";


type GeometricToleranceEditorProps = {
  item: GeometricToleranceReviewItem;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  disabled?: boolean;
};

const GDT_TYPES: Array<{ value: GeometricToleranceType; label: string }> =
  Object.entries(zhCN.inspection.gdtTypes).map(([value, label]) => ({
    value: value as GeometricToleranceType,
    label,
  }));

const MODIFIER_OPTIONS: Array<{
  value: GdtModifier["kind"] | "none";
  label: string;
  rawSymbol?: string;
}> = [
  { value: "none", label: zhCN.inspection.gdtEditor.noModifier },
  {
    value: "maximum_material_condition",
    label: zhCN.inspection.gdtModifiers.maximum_material_condition,
    rawSymbol: "Ⓜ",
  },
  {
    value: "least_material_condition",
    label: zhCN.inspection.gdtModifiers.least_material_condition,
    rawSymbol: "Ⓛ",
  },
  {
    value: "regardless_of_feature_size",
    label: zhCN.inspection.gdtModifiers.regardless_of_feature_size,
    rawSymbol: "Ⓢ",
  },
  {
    value: "unknown",
    label: zhCN.inspection.gdtModifiers.unknown,
  },
];

const DECIMAL_PATTERN = /^(?:\d+(?:\.\d*)?|\.\d+)$/;

function copyModifier(modifier: GdtModifier): GdtModifier {
  return { kind: modifier.kind, raw_symbol: modifier.raw_symbol };
}

function copyDatum(datum: GdtDatumReference): GdtDatumReference {
  return {
    datum: datum.datum,
    modifiers: datum.modifiers?.map(copyModifier) ?? [],
  };
}

function copySegment(segment: GdtSegment): GdtSegment {
  return {
    tolerance_value: String(segment.tolerance_value),
    diameter_modifier: segment.diameter_modifier,
    modifiers: segment.modifiers?.map(copyModifier) ?? [],
    datum_references: segment.datum_references?.map(copyDatum) ?? [],
  };
}

function copyFrames(item: GeometricToleranceReviewItem): GdtFrame[] {
  if (item.frames.length > 0) {
    return item.frames.map((frame) => ({
      segments: frame.segments.map(copySegment),
    }));
  }
  return [{
    segments: [{
      tolerance_value: "",
      diameter_modifier: false,
      modifiers: [],
      datum_references: [],
    }],
  }];
}

function modifierValue(segment: GdtSegment): GdtModifier["kind"] | "none" {
  return segment.modifiers?.[0]?.kind ?? "none";
}

function withSegment(
  frames: GdtFrame[],
  frameIndex: number,
  segmentIndex: number,
  update: (segment: GdtSegment) => GdtSegment,
): GdtFrame[] {
  return frames.map((frame, currentFrameIndex) => {
    if (currentFrameIndex !== frameIndex) return frame;
    return {
      segments: frame.segments.map((segment, currentSegmentIndex) =>
        currentSegmentIndex === segmentIndex ? update(segment) : segment,
      ),
    };
  });
}

function datumReference(datum: string): GdtDatumReference {
  return { datum, modifiers: [] };
}

export function GeometricToleranceEditor({
  item,
  onCommand,
  disabled = false,
}: GeometricToleranceEditorProps) {
  const [toleranceType, setToleranceType] = useState<GeometricToleranceType>(
    item.frames.length === 0 ? "unknown" : item.tolerance_type,
  );
  const [frames, setFrames] = useState<GdtFrame[]>(() => copyFrames(item));
  const [error, setError] = useState<string>();

  const updateSegment = (
    frameIndex: number,
    segmentIndex: number,
    update: (segment: GdtSegment) => GdtSegment,
  ) => {
    setFrames((current) => withSegment(
      current,
      frameIndex,
      segmentIndex,
      update,
    ));
  };

  const save = () => {
    for (const frame of frames) {
      for (const segment of frame.segments) {
        const value = String(segment.tolerance_value).trim();
        if (!DECIMAL_PATTERN.test(value) || Number(value) <= 0) {
          setError(zhCN.inspection.gdtEditor.invalidValue);
          return;
        }
        for (const datum of segment.datum_references ?? []) {
          if (!/^[A-Z]$/.test(datum.datum.trim())) {
            setError(zhCN.inspection.gdtEditor.invalidDatum);
            return;
          }
        }
      }
    }
    setError(undefined);
    const command: EditGeometricTolerance = {
      type: "edit_geometric_tolerance",
      item_id: item.item_id,
      tolerance_type: toleranceType,
      frames,
      standard_context: "unspecified",
    };
    void onCommand(command);
  };

  return (
    <fieldset className="gdt-editor" disabled={disabled}>
      <legend>{zhCN.inspection.gdtEditor.title}</legend>
      {item.frames.length === 0 ? (
        <p className="gdt-editor__unknown">
          {zhCN.inspection.gdtTypes.unknown}：{item.raw_text} · {zhCN.inspection.gdtEditor.unknownHint}
        </p>
      ) : null}
      <label>
        {zhCN.inspection.gdtEditor.subtype}
        <select
          aria-label={zhCN.inspection.gdtEditor.subtype}
          value={toleranceType}
          onChange={(event) =>
            setToleranceType(event.target.value as GeometricToleranceType)}
        >
          {GDT_TYPES.map((type) => (
            <option key={type.value} value={type.value}>{type.label}</option>
          ))}
        </select>
      </label>
      {frames.map((frame, frameIndex) => (
        <div className="gdt-editor__frame" key={`frame-${frameIndex}`}>
          <h4>{zhCN.inspection.gdtEditor.frame(frameIndex + 1)}</h4>
          {frame.segments.map((segment, segmentIndex) => {
            const segmentNumber = frame.segments.length > 1
              ? ` ${frameIndex + 1}.${segmentIndex + 1}`
              : frameIndex === 0
                ? ""
                : ` ${frameIndex + 1}`;
            return (
              <div
                className="gdt-editor__segment"
                key={`segment-${frameIndex}-${segmentIndex}`}
              >
                <label>
                  {zhCN.inspection.gdtEditor.toleranceValue}{segmentNumber}
                  <input
                    aria-label={`${zhCN.inspection.gdtEditor.toleranceValue}${segmentNumber}`}
                    inputMode="decimal"
                    type="text"
                    value={String(segment.tolerance_value)}
                    onChange={(event) => updateSegment(
                      frameIndex,
                      segmentIndex,
                      (current) => ({
                        ...current,
                        tolerance_value: event.target.value,
                      }),
                    )}
                  />
                </label>
                <label className="gdt-editor__checkbox">
                  <input
                    type="checkbox"
                    checked={segment.diameter_modifier}
                    onChange={(event) => updateSegment(
                      frameIndex,
                      segmentIndex,
                      (current) => ({
                        ...current,
                        diameter_modifier: event.target.checked,
                      }),
                    )}
                  />
                  {zhCN.inspection.gdtEditor.diameterModifier}
                </label>
                <label>
                  {zhCN.inspection.gdtEditor.modifier}
                  <select
                    aria-label={`${zhCN.inspection.gdtEditor.modifier}${segmentNumber}`}
                    value={modifierValue(segment)}
                    onChange={(event) => updateSegment(
                      frameIndex,
                      segmentIndex,
                      (current) => {
                        const option = MODIFIER_OPTIONS.find(
                          (candidate) => candidate.value === event.target.value,
                        );
                        return {
                          ...current,
                          modifiers: option === undefined || option.value === "none"
                            ? []
                            : [{
                                kind: option.value,
                                raw_symbol: option.rawSymbol ?? "?",
                              }],
                        };
                      },
                    )}
                  >
                    {MODIFIER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="gdt-editor__datums">
                  {(segment.datum_references ?? []).map((datum, datumIndex) => (
                    <label key={`datum-${datumIndex}`}>
                      {zhCN.inspection.gdtEditor.datum(datumIndex + 1)}
                      <input
                        aria-label={zhCN.inspection.gdtEditor.datum(datumIndex + 1)}
                        maxLength={1}
                        type="text"
                        value={datum.datum}
                        onChange={(event) => updateSegment(
                          frameIndex,
                          segmentIndex,
                          (current) => ({
                            ...current,
                            datum_references: (current.datum_references ?? []).map(
                              (currentDatum, currentDatumIndex) =>
                                currentDatumIndex === datumIndex
                                  ? { ...currentDatum, datum: event.target.value }
                                  : currentDatum,
                            ),
                          }),
                        )}
                      />
                    </label>
                  ))}
                  <button
                    type="button"
                    className="gdt-editor__add-datum"
                    onClick={() => updateSegment(
                      frameIndex,
                      segmentIndex,
                      (current) => ({
                        ...current,
                        datum_references: [
                          ...(current.datum_references ?? []),
                          datumReference(""),
                        ],
                      }),
                    )}
                  >
                    + {zhCN.inspection.gdtEditor.datum(
                      (segment.datum_references ?? []).length + 1,
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ))}
      {error ? <p className="gdt-editor__error" role="alert">{error}</p> : null}
      <button
        type="button"
        className="review-command-rail__primary"
        onClick={save}
      >
        {zhCN.inspection.gdtEditor.save}
      </button>
    </fieldset>
  );
}
