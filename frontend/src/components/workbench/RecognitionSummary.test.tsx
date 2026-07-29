import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { RecognitionSummary } from "./RecognitionSummary";


afterEach(cleanup);

test("P0-UI-004 derives active, excluded and manual-required filters from project data", () => {
  const onFilterChange = vi.fn();
  render(
    <RecognitionSummary
      items={[
        { item_id: "i1", raw_text: "M6", active: true },
        { item_id: "i2", raw_text: "M8", active: true },
        { item_id: "i3", raw_text: "M10", active: false },
      ]}
      balloons={[
        {
          id: "b1",
          itemId: "i1",
          sourceId: "s1",
          pageIndex: 0,
          center: [30, 30],
          number: 1,
          version: 1,
          status: "active",
          sortOrder: 0,
          placementStatus: "placed",
          collisionFlags: [],
          leaderTarget: [20, 20],
        },
        {
          id: "b2",
          itemId: "i2",
          sourceId: "s2",
          pageIndex: 0,
          center: [70, 70],
          number: 2,
          version: 1,
          status: "active",
          sortOrder: 1,
          placementStatus: "manual_required",
          collisionFlags: ["circle_overlap"],
          leaderTarget: [60, 60],
        },
      ]}
      pendingSourceCount={2}
      filter="all"
      onFilterChange={onFilterChange}
    />,
  );

  expect(screen.getByRole("button", { name: "筛选全部" }).textContent)
    .toContain("5");
  expect(screen.getByTestId("summary-active-count").textContent).toBe("2");
  expect(screen.getByTestId("summary-excluded-count").textContent).toBe("1");
  expect(screen.getByTestId("summary-manual-count").textContent).toBe("2");
  expect(screen.getByRole("button", { name: "筛选有效项" })).not.toBeNull();

  const pendingChip = screen.getByRole("button", { name: "筛选待确认来源" });
  expect(pendingChip.classList.contains("summary-chip--pending_sources"))
    .toBe(true);
  fireEvent.click(pendingChip);
  expect(onFilterChange).toHaveBeenCalledWith("manual_required");
  for (const label of ["全部", "有效项", "已排除", "待确认来源", "硬碰撞"]) {
    expect(screen.getByRole("region", { name: "识别汇总" }).textContent)
      .toContain(label);
  }
});

test("待确认来源清零后恢复气泡人工处理统计", () => {
  render(
    <RecognitionSummary
      items={[{ item_id: "i1", raw_text: "M6", active: true }]}
      balloons={[{
        id: "b1",
        itemId: "i1",
        sourceId: "s1",
        pageIndex: 0,
        center: [30, 30],
        number: 1,
        version: 1,
        status: "active",
        sortOrder: 0,
        placementStatus: "manual_required",
        collisionFlags: [],
        leaderTarget: [20, 20],
      }]}
      pendingSourceCount={0}
      filter="all"
      onFilterChange={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "筛选需人工处理" }))
    .not.toBeNull();
  expect(screen.getByTestId("summary-manual-count").textContent).toBe("1");
});
