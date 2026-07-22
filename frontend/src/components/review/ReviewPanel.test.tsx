import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { ReviewPanel } from "./ReviewPanel";


describe("ReviewPanel", () => {
  test("P0-UI-006 exposes all eight review commands only on explicit actions", () => {
    const onCommand = vi.fn();
    render(
      <ReviewPanel
        items={[
          {
            item_id: "i1",
            item_type: "thread",
            raw_text: "M6",
            coordinates: [1, 2, 3, 4],
            scope: "local_feature",
            balloon_required: true,
            requires_confirmation: false,
            active: true,
          },
          {
            item_id: "i2",
            item_type: "thread",
            raw_text: "M6 通",
            coordinates: [5, 6, 7, 8],
            scope: "local_feature",
            balloon_required: false,
            requires_confirmation: false,
            active: true,
          },
          {
            item_id: "typed-1",
            item_type: "linear_dimension",
            raw_text: "10 ±0.02",
            nominal: "10",
            upper_tolerance: "0.02",
            coordinates: [5, 6, 7, 8],
            scope: "local_feature",
            balloon_required: true,
            requires_confirmation: false,
            active: true,
          },
          {
            item_id: "complex-1",
            raw_text: "Ra 3.2",
            coordinates: [9, 10, 11, 12],
            coarse_type: "roughness",
            requires_confirmation: true,
            active: true,
          },
        ]}
        onCommand={onCommand}
      />,
    );

    expect(onCommand).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep i1" }));
    fireEvent.click(screen.getByRole("button", { name: "Exclude i1" }));
    fireEvent.change(screen.getByLabelText("Raw text typed-1"), {
      target: { value: "12.50 +0.03" },
    });
    fireEvent.change(screen.getByLabelText("Nominal typed-1"), {
      target: { value: "12.50" },
    });
    fireEvent.change(screen.getByLabelText("Upper tolerance typed-1"), {
      target: { value: "0.03" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Edit typed-1" }));

    fireEvent.change(screen.getByLabelText("Raw text complex-1"), {
      target: { value: "Ra 1.6" },
    });
    fireEvent.change(screen.getByLabelText("Coordinates complex-1"), {
      target: { value: "11,12,13,14" },
    });
    fireEvent.change(screen.getByLabelText("Coarse type complex-1"), {
      target: { value: "weld" },
    });
    fireEvent.click(screen.getByLabelText("Requires confirmation field complex-1"));
    fireEvent.click(screen.getByRole("button", { name: "Edit complex-1" }));

    fireEvent.change(screen.getByLabelText("Manual raw text"), {
      target: { value: "M8" },
    });
    fireEvent.change(screen.getByLabelText("Manual coordinates"), {
      target: { value: "10,20,30,40" },
    });
    fireEvent.change(screen.getByLabelText("Manual item type"), {
      target: { value: "diameter_dimension" },
    });
    fireEvent.click(screen.getByLabelText("Manual balloon required"));
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));

    fireEvent.click(screen.getByLabelText("Select i1"));
    fireEvent.click(screen.getByLabelText("Select i2"));
    fireEvent.click(screen.getByRole("button", { name: "Merge selected" }));
    fireEvent.change(screen.getByLabelText("Split parts i1"), {
      target: { value: "M6|深10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Split i1" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Accept confirmation complex-1" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Reject confirmation complex-1" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Set balloon not required i1" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Require balloon i2" }),
    );

    const commands = onCommand.mock.calls.map(([command]) => command);
    expect(new Set(commands.map((command) => command.type))).toEqual(
      new Set([
        "keep",
        "exclude",
        "edit",
        "add",
        "merge",
        "split",
        "resolve_confirmation",
        "set_balloon_required",
      ]),
    );
    expect(commands.find((command) => command.type === "add")).toMatchObject({
      coordinates: [10, 20, 30, 40],
      scope: "local_feature",
      item_type: "diameter_dimension",
      balloon_required: false,
    });
    expect(
      commands.find(
        (command) => command.type === "edit" && command.item_id === "typed-1",
      ),
    ).toMatchObject({
      fields: {
        raw_text: "12.50 +0.03",
        nominal: "12.50",
        upper_tolerance: "0.03",
      },
    });
    const complexEdit = commands.find(
      (command) => command.type === "edit" && command.item_id === "complex-1",
    );
    if (complexEdit === undefined || complexEdit.type !== "edit") {
      throw new Error("complex edit command was not emitted");
    }
    expect(complexEdit).toMatchObject({
      fields: {
        raw_text: "Ra 1.6",
        coordinates: [11, 12, 13, 14],
        coarse_type: "weld",
        requires_confirmation: false,
      },
    });
    expect(Object.keys(complexEdit.fields).sort()).toEqual([
      "coarse_type",
      "coordinates",
      "raw_text",
      "requires_confirmation",
    ]);
    expect(
      commands
        .filter((command) => command.type === "resolve_confirmation")
        .map((command) => command.accepted),
    ).toEqual([true, false]);
    expect(
      commands
        .filter((command) => command.type === "set_balloon_required")
        .map((command) => command.balloon_required),
    ).toEqual([false, true]);
  });
});
