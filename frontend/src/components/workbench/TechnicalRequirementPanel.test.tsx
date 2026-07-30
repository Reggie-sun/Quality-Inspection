import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { TechnicalRequirement } from "../../api/types";
import { TechnicalRequirementPanel } from "./TechnicalRequirementPanel";


afterEach(cleanup);

function requirement(
  requirementId: string,
  rawText: string,
  overrides: Partial<TechnicalRequirement> = {},
): TechnicalRequirement {
  return {
    requirement_id: requirementId,
    ordinal: 1,
    raw_text: rawText,
    normalized_text: rawText,
    source_location_ids: [`source-${requirementId}`],
    page_index: 0,
    category: "applicability_rule",
    subtype: "general_dimensional_tolerance",
    parsed_parameters: {},
    match_outcome: "unresolved",
    matched_candidate_ids: [],
    rule_version: "technical-requirement/1",
    review_required: true,
    ...overrides,
  };
}

test("显示 matched、global 和 unresolved 技术要求状态", () => {
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement(
          "matched",
          "未注尺寸公差按 GB/T 1804-m 执行",
          {
            match_outcome: "matched_items",
            matched_candidate_ids: ["dimension-25", "dimension-30"],
            review_required: false,
            review_status: "confirmed",
          },
        ),
        requirement("global", "锐边去毛刺", {
          category: "standalone_check",
          subtype: "deburr",
          match_outcome: "global_scope",
          generated_candidate_id: "global-deburr",
          review_required: false,
          review_status: "confirmed",
        }),
        requirement("pending", "未注形位公差按 GB/T 1184-k 执行"),
      ]}
      items={[
        {
          item_id: "dimension-25",
          raw_text: "25",
          item_type: "linear_dimension",
          active: true,
        },
        {
          item_id: "dimension-30",
          raw_text: "30",
          item_type: "linear_dimension",
          active: true,
        },
      ]}
      onSelectItem={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "展开技术要求" })
    .getAttribute("aria-expanded")).toBe("false");
  expect(screen.getByText("3 条")).not.toBeNull();
  expect(screen.getByText("待确认 1")).not.toBeNull();
  expect(screen.queryByText("未注尺寸公差按 GB/T 1804-m 执行")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));

  expect(screen.getByRole("button", { name: "收起技术要求" })
    .getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("未注尺寸公差按 GB/T 1804-m 执行")).not.toBeNull();
  expect(screen.getByText("已匹配 2 项")).not.toBeNull();
  expect(screen.getByText("全局要求")).not.toBeNull();
  expect(screen.getByText("待确认")).not.toBeNull();
});

test("待确认匹配提供明确确认按钮并复用唯一 review command", () => {
  const onSelectItem = vi.fn();
  const onCommand = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("requirement-matched", "尺寸规则", {
          match_outcome: "matched_items",
          matched_candidate_ids: ["dimension-25"],
        }),
        requirement(
          "requirement-5",
          "未注尺寸公差按 GB/T 1804-m 执行",
        ),
      ]}
      items={[{
        item_id: "dimension-25",
        raw_text: "25",
        item_type: "linear_dimension",
        active: true,
      }]}
      onSelectItem={onSelectItem}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  fireEvent.click(screen.getByRole("button", {
    name: "查看匹配检验项：25",
  }));
  expect(onSelectItem).toHaveBeenCalledWith("dimension-25");

  const pendingRequirement = screen.getByText(
    "未注尺寸公差按 GB/T 1804-m 执行",
  ).closest("li");
  expect(pendingRequirement).not.toBeNull();
  fireEvent.click(within(pendingRequirement!).getByRole("button", {
    name: "确认匹配此检验项：25",
  }));
  expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "requirement-5",
    outcome: "matched_items",
    matched_item_ids: ["dimension-25"],
  });
});

test("已有自动建议计入待确认并可原样确认", () => {
  const onCommand = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("matched-suggestion", "未注尺寸公差", {
          match_outcome: "matched_items",
          matched_candidate_ids: ["dimension-25", "dimension-30"],
          review_status: "suggested",
        }),
        requirement("global-suggestion", "锐边去毛刺", {
          category: "standalone_check",
          subtype: "deburr",
          match_outcome: "global_scope",
          generated_candidate_id: "global-deburr",
          review_status: "suggested",
        }),
      ]}
      items={[
        {
          item_id: "dimension-25",
          raw_text: "25",
          item_type: "linear_dimension",
          active: true,
        },
        {
          item_id: "dimension-30",
          raw_text: "30",
          item_type: "linear_dimension",
          active: true,
        },
        {
          item_id: "global-deburr",
          raw_text: "锐边去毛刺",
          item_type: "general_requirement",
          active: true,
        },
      ]}
      onSelectItem={vi.fn()}
      onCommand={onCommand}
    />,
  );

  expect(screen.getByText("待确认 2")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));

  const matchedSuggestion = screen.getByText("未注尺寸公差").closest("li");
  expect(matchedSuggestion).not.toBeNull();
  fireEvent.click(within(matchedSuggestion!).getByRole("button", {
    name: "确认当前匹配（2 项）",
  }));
  expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "matched-suggestion",
    outcome: "matched_items",
    matched_item_ids: ["dimension-25", "dimension-30"],
  });

  const globalSuggestion = screen.getByText("锐边去毛刺").closest("li");
  expect(globalSuggestion).not.toBeNull();
  fireEvent.click(within(globalSuggestion!).getByRole("button", {
    name: "确认设为全局要求",
  }));
  expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "global-suggestion",
    outcome: "global_scope",
  });
});
