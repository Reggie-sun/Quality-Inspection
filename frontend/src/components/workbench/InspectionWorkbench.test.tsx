import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { InspectionWorkbench } from "./InspectionWorkbench";


afterEach(cleanup);

describe("InspectionWorkbench", () => {
  test("P0-UI-007 keeps one pending command stable until explicit Save", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
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
        ]}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Keep i1" }));

    expect(screen.getByText("Pending command: keep")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "Exclude i1" }).getAttribute("disabled"),
    ).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Exclude i1" }));
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save working copy" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({ type: "keep", item_id: "i1" });
      expect(screen.getByText("Working copy saved")).not.toBeNull();
    });
    expect(
      screen.getByRole("button", { name: "Exclude i1" }).getAttribute("disabled"),
    ).toBeNull();
  });

  test("P0-UI-007 submits Save only once while the request is in flight", async () => {
    let resolveSave!: () => void;
    const onSave = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSave = resolve;
        }),
    );
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[
          {
            item_id: "i1",
            item_type: "thread",
            raw_text: "M6",
            active: true,
          },
        ]}
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Keep i1" }));
    const save = screen.getByRole("button", { name: "Save working copy" });

    fireEvent.click(save);
    fireEvent.click(save);

    expect(save.getAttribute("disabled")).not.toBeNull();
    expect(onSave).toHaveBeenCalledOnce();

    resolveSave();
    await waitFor(() => expect(screen.getByText("Working copy saved")).not.toBeNull());
  });
});
