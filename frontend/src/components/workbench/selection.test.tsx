import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { InspectionWorkbench } from "./InspectionWorkbench";
import { relatedItemIds } from "./selection";


afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("P0-BAL-013 table, source and balloon selection share item identity", () => {
  const scrollIntoView = vi.fn();
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  render(
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[
        { id: "candidate-i1", itemId: "i1", pageIndex: 0, bbox: [10, 20, 30, 40] },
        { id: "candidate-i2", itemId: "i2", pageIndex: 0, bbox: [50, 60, 70, 80] },
      ]}
      sources={[
        { id: "s1", itemIds: ["i1"], pageIndex: 0, bbox: [10, 20, 30, 40] },
        { id: "s2", itemIds: ["i2"], pageIndex: 0, bbox: [50, 60, 70, 80] },
      ]}
      balloons={[
        {
          id: "b1",
          itemId: "i1",
          sourceId: "s1",
          pageIndex: 0,
          center: [50, 60],
          number: 1,
          version: 1,
          status: "active",
          sortOrder: 0,
        },
        {
          id: "b2",
          itemId: "i2",
          sourceId: "s2",
          pageIndex: 0,
          center: [80, 90],
          number: 2,
          version: 1,
          status: "active",
          sortOrder: 1,
        },
      ]}
      items={[
        {
          item_id: "i1",
          item_type: "thread",
          raw_text: "M6",
          active: true,
        },
        {
          item_id: "i2",
          item_type: "thread",
          raw_text: "M8",
          active: true,
        },
      ]}
      onSave={vi.fn().mockResolvedValue(undefined)}
      onDeleteBalloon={vi.fn()}
      onRebuildBalloon={vi.fn()}
      onReorderBalloon={vi.fn()}
      onRenumberBalloons={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("row", { name: /M6/ }));

  expect(screen.getByTestId("source-s1").getAttribute("data-selected")).toBe("true");
  expect(screen.getByTestId("balloon-b1").getAttribute("data-selected")).toBe("true");
  expect(scrollIntoView).toHaveBeenCalled();

  fireEvent.click(screen.getByTestId("balloon-b1"));
  expect(screen.getByRole("button", { name: "Delete balloon" }).hasAttribute("disabled"))
    .toBe(false);

  fireEvent.click(screen.getByRole("row", { name: /M8/ }));
  expect(screen.getByTestId("candidate-candidate-i2").getAttribute("data-selected"))
    .toBe("true");
  expect(screen.getByTestId("source-s2").getAttribute("data-selected")).toBe("true");
  expect(screen.getByTestId("balloon-b1").getAttribute("data-selected")).toBe("false");
  expect(screen.getByTestId("balloon-b2").getAttribute("data-selected")).toBe("true");
  expect(screen.getByRole("button", { name: "Delete balloon" }).hasAttribute("disabled"))
    .toBe(true);

  fireEvent.click(screen.getByTestId("source-s1"));
  expect(screen.getByRole("row", { name: /M6/ }).getAttribute("data-selected")).toBe(
    "true",
  );
  expect(screen.getByTestId("balloon-b2").getAttribute("data-selected")).toBe("false");
  expect(screen.getByRole("button", { name: "Delete balloon" }).hasAttribute("disabled"))
    .toBe(true);

  fireEvent.click(screen.getByTestId("candidate-candidate-i2"));
  expect(screen.getByRole("row", { name: /M8/ }).getAttribute("data-selected")).toBe(
    "true",
  );
  expect(relatedItemIds({ itemId: "i1" })).toEqual(["i1"]);
  expect(relatedItemIds({ itemIds: ["i2", "i1"] })).toEqual(["i2", "i1"]);
});
