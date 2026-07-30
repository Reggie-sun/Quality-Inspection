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
      manualReviewCount={2}
      pendingSourceCount={2}
      filter="all"
      onFilterChange={onFilterChange}
    />,
  );

  expect(screen.getByRole("button", { name: "筛选全部" }).textContent)
    .toContain("5");
  expect(screen.getByTestId("summary-active-count").textContent).toBe("2");
  expect(screen.getByTestId("summary-excluded-count").textContent).toBe("1");
  expect(screen.getByTestId("summary-review-count").textContent).toBe("2");
  expect(screen.getByTestId("summary-manual-count").textContent).toBe("1");
  expect(screen.getByRole("button", { name: "筛选有效项" })).not.toBeNull();

  const reviewChip = screen.getByRole("button", { name: "筛选待人工审核" });
  fireEvent.click(reviewChip);
  expect(onFilterChange).toHaveBeenCalledWith("review_required");
  for (const label of [
    "全部",
    "有效项",
    "已排除",
    "自动通过",
    "待人工审核",
    "需人工处理",
    "硬碰撞",
  ]) {
    expect(screen.getByRole("region", { name: "识别汇总" }).textContent)
      .toContain(label);
  }
});

test("气泡人工放置统计不依赖待确认来源", () => {
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

test("已保留但未选择气泡的项目继续计入待人工审核", () => {
  render(
    <RecognitionSummary
      items={[{
        item_id: "balloon-pending",
        raw_text: "3.2",
        status: "kept",
        requires_confirmation: false,
        balloon_required: null,
        active: true,
      }]}
      balloons={[]}
      manualReviewCount={0}
      filter="review_required"
      onFilterChange={vi.fn()}
    />,
  );

  expect(screen.getByTestId("summary-review-count").textContent).toBe("1");
});

test("自动通过、人工审核、放置人工处理与碰撞计数彼此独立", () => {
  const onFilterChange = vi.fn();
  render(
    <RecognitionSummary
      items={[
        {
          item_id: "auto",
          raw_text: "10",
          status: "auto_accepted",
          requires_confirmation: false,
          balloon_required: true,
          acceptance_source: "confidence_policy",
          confidence_decision: {
            band: "high",
            review_disposition: "auto_accepted",
            policy_version: "candidate-confidence/1",
            evidence_codes: ["typed_schema_complete"],
          },
          active: true,
        },
        {
          item_id: "manual",
          raw_text: "20",
          status: "pending",
          confidence_decision: {
            band: "medium",
            review_disposition: "review_required",
            policy_version: "candidate-confidence/1",
            evidence_codes: ["typed_schema_complete"],
          },
          active: true,
        },
      ]}
      balloons={[
        {
          id: "placement",
          itemId: "manual",
          center: [20, 20],
          number: 2,
          status: "active",
          placementStatus: "manual_required",
          collisionFlags: ["circle_overlap"],
        },
      ]}
      manualReviewCount={3}
      pendingSourceCount={4}
      filter="review_required"
      onFilterChange={onFilterChange}
    />,
  );

  expect(screen.getByTestId("summary-auto-count").textContent).toBe("1");
  expect(screen.getByTestId("summary-review-count").textContent).toBe("3");
  expect(screen.getByTestId("summary-manual-count").textContent).toBe("1");
  expect(screen.getByTestId("summary-collision-count").textContent).toBe("1");
  expect(screen.getByRole("button", { name: "筛选待人工审核" })
    .getAttribute("data-active")).toBe("true");

  fireEvent.click(screen.getByRole("button", { name: "筛选自动通过" }));
  expect(onFilterChange).toHaveBeenCalledWith("auto_accepted");
});
