import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { InspectionItemTable } from "./InspectionItemTable";


afterEach(cleanup);

test("P0-UI-004 keeps the dense list and drawing selection on one item identity", () => {
  const onSelectItem = vi.fn();
  const props = {
    items: [
      {
        item_id: "i1",
        raw_text: "10 ±0.02",
        item_type: "linear_dimension" as const,
        nominal: "10",
        upper_tolerance: "0.02",
        lower_tolerance: "-0.02",
        page_index: 0,
        active: true,
      },
      {
        item_id: "i2",
        raw_text: "M8",
        item_type: "thread" as const,
        page_index: 1,
        active: true,
      },
    ],
    balloons: [
      {
        id: "b1",
        itemId: "i1",
        sourceId: "s1",
        pageIndex: 0,
        center: [30, 30] as [number, number],
        number: 7,
        version: 1,
        status: "active" as const,
        sortOrder: 0,
        placementStatus: "manual_required" as const,
        collisionFlags: ["protected_overlap"],
        leaderTarget: [20, 20] as [number, number],
      },
    ],
    filter: "all" as const,
    onSelectItem,
  };
  const { rerender } = render(
    <InspectionItemTable {...props} selectedItemId="i1" />,
  );

  const row = screen.getByRole("row", { name: /10 ±0.02/ });
  expect(row.getAttribute("data-selected")).toBe("true");
  expect(row.textContent).toContain("7");
  expect(row.textContent).toContain("linear dimension");
  expect(row.textContent).toContain("10");
  expect(row.textContent).toContain("+0.02 / -0.02");
  expect(row.textContent).toContain("Page 1");
  expect(row.textContent).toContain("Manual required");
  expect(row.textContent).toContain("protected overlap");

  fireEvent.click(screen.getByRole("row", { name: /M8/ }));
  expect(onSelectItem).toHaveBeenCalledWith("i2");

  rerender(<InspectionItemTable {...props} selectedItemId="i2" />);
  expect(screen.getByRole("row", { name: /M8/ }).getAttribute("data-selected"))
    .toBe("true");
  expect(screen.getByRole("row", { name: /10 ±0.02/ }).getAttribute("data-selected"))
    .toBe("false");
});
