import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type {
  GeometricToleranceReviewItem,
  ReviewCommand,
} from "../../api/types";
import { GeometricToleranceEditor } from "./GeometricToleranceEditor";


afterEach(cleanup);

const item: GeometricToleranceReviewItem = {
  item_id: "gdt-editor",
  item_type: "geometric_tolerance",
  schema_version: "geometric-tolerance-candidate/1",
  raw_text: "∥ 0.1 A",
  normalized_text: "∥ | 0.1 | A",
  coordinates: [1, 2, 3, 4],
  tolerance_type: "parallelism",
  tolerance_symbol: "∥",
  tolerance_value: "0.1",
  diameter_modifier: false,
  modifiers: [],
  datum_references: [{ datum: "A", modifiers: [] }],
  frames: [{
    segments: [{
      tolerance_value: "0.1",
      diameter_modifier: false,
      modifiers: [],
      datum_references: [{ datum: "A", modifiers: [] }],
    }],
  }],
  standard_context: "unspecified",
  evidence_ref: "asset://gdt-editor",
  source_location_ids: ["gdt-source"],
  source_type: "automatic",
  status: "pending",
  requires_confirmation: true,
};

test("submits ordered structured fields without parsing raw_text", () => {
  const onCommand = vi.fn<(command: ReviewCommand) => void>();
  render(<GeometricToleranceEditor item={item} onCommand={onCommand} />);

  fireEvent.change(screen.getByLabelText("公差值"), {
    target: { value: "0.12" },
  });
  fireEvent.change(screen.getByLabelText("基准 1"), {
    target: { value: "B" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存几何公差" }));

  expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({
    type: "edit_geometric_tolerance",
    item_id: "gdt-editor",
    tolerance_type: "parallelism",
    frames: [{
      segments: [{
        tolerance_value: "0.12",
        diameter_modifier: false,
        modifiers: [],
        datum_references: [{ datum: "B", modifiers: [] }],
      }],
    }],
  }));
});

test("rejects non-positive decimal before submitting", () => {
  const onCommand = vi.fn();
  render(<GeometricToleranceEditor item={item} onCommand={onCommand} />);

  fireEvent.change(screen.getByLabelText("公差值"), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存几何公差" }));

  expect(onCommand).not.toHaveBeenCalled();
  expect(screen.getByRole("alert").textContent).toContain("请输入大于 0 的小数");
});

test("empty frames stay manual until a typed structure is submitted", () => {
  const onCommand = vi.fn<(command: ReviewCommand) => void>();
  render(
    <GeometricToleranceEditor
      item={{ ...item, tolerance_type: "unknown", frames: [], raw_text: "∥ ? A" }}
      onCommand={onCommand}
    />,
  );

  expect(screen.getByText(/未确认几何公差：∥ \? A/)).toBeDefined();
  fireEvent.change(screen.getByLabelText("公差值"), {
    target: { value: "0.2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存几何公差" }));

  expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({
    type: "edit_geometric_tolerance",
    tolerance_type: "unknown",
  }));
});
