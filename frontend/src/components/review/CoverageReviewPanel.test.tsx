import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CoverageReviewPanel } from "./CoverageReviewPanel";


afterEach(cleanup);

describe("CoverageReviewPanel", () => {
  test("逐条展示真实来源并提交既有确认命令", async () => {
    const onCommand = vi.fn();
    const onSelectSource = vi.fn();
    render(
      <CoverageReviewPanel
        entries={[
          {
            observation_id: "hidden-observation-id",
            source_location_id: "hidden-source-id",
            candidate_id: null,
            disposition: "ambiguous",
            coordinates: [60, 70, 150, 84],
            requires_confirmation: true,
          },
          {
            observation_id: "hidden-observation-id-2",
            source_location_id: "hidden-source-id-2",
            candidate_id: null,
            disposition: "ambiguous",
            coordinates: [20, 30, 40, 50],
            requires_confirmation: true,
          },
        ]}
        sources={[
          {
            id: "hidden-source-id",
            pageIndex: 1,
            bbox: [60, 70, 150, 84],
            rawText: "技术要求：去除毛刺",
          },
          {
            id: "hidden-source-id-2",
            pageIndex: 0,
            bbox: [20, 30, 40, 50],
            rawText: "表面不得有划伤",
          },
        ]}
        onCommand={onCommand}
        onSelectSource={onSelectSource}
      />,
    );

    const region = screen.getByRole("region", { name: "来源待确认" });
    expect(region.textContent).toContain("1 / 2");
    expect(region.textContent).toContain("技术要求：去除毛刺");
    expect(region.textContent).toContain("第 2 页");
    expect(region.textContent).not.toContain("hidden-observation-id");
    expect(region.textContent).not.toContain("hidden-source-id");
    await waitFor(() => {
      expect(onSelectSource).toHaveBeenCalledWith("hidden-source-id");
    });

    fireEvent.click(screen.getByRole("button", { name: "下一条来源" }));
    expect(region.textContent).toContain("2 / 2");
    expect(region.textContent).toContain("表面不得有划伤");
    fireEvent.click(screen.getByRole("button", { name: "确认忽略此来源" }));

    expect(onCommand).toHaveBeenCalledWith({
      type: "resolve_confirmation",
      item_id: "hidden-observation-id-2",
      accepted: false,
    });
  });

  test("缺失来源投影时使用空值而不伪造第一页", () => {
    render(
      <CoverageReviewPanel
        entries={[{
          observation_id: "missing-observation",
          source_location_id: "missing-source",
          candidate_id: null,
          disposition: "ambiguous",
          coordinates: [1, 2, 3, 4],
          requires_confirmation: true,
        }]}
        sources={[]}
        onCommand={vi.fn()}
        onSelectSource={vi.fn()}
      />,
    );

    const region = screen.getByRole("region", { name: "来源待确认" });
    expect(region.textContent).toContain("—");
    expect(region.textContent).not.toContain("第 1 页");
  });
});
