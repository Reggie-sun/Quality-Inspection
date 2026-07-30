import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
  expect(screen.getAllByText("已确认")).toHaveLength(2);
  expect(screen.getByText("已应用到 2 个检验项")).not.toBeNull();
  expect(screen.getByText("已确认为全局 SIP 要求")).not.toBeNull();
  expect(screen.getByText("待确认")).not.toBeNull();
});

test("系统建议先形成草稿，预览影响后才提交并进入下一条", async () => {
  const onCommand = vi.fn();
  const props = {
    items: [
      {
        item_id: "dimension-25",
        raw_text: "25",
        item_type: "linear_dimension" as const,
        active: true,
      },
      {
        item_id: "dimension-30",
        raw_text: "30",
        item_type: "linear_dimension" as const,
        active: true,
      },
    ],
    onSelectItem: vi.fn(),
    onCommand,
  };
  const { rerender } = render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("requirement-matched", "尺寸规则", {
          match_outcome: "matched_items",
          matched_candidate_ids: ["dimension-25", "dimension-30"],
          review_status: "suggested",
        }),
        requirement("requirement-next", "下一条要求"),
      ]}
      {...props}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  const current = screen.getByText("尺寸规则").closest("li");
  expect(current).not.toBeNull();
  const confirm = within(current!).getByRole("button", {
    name: "请先选择处理方式",
  });
  expect(confirm.getAttribute("disabled")).not.toBeNull();

  fireEvent.click(within(current!).getByRole("radio", {
    name: "应用到系统建议的检验项",
  }));
  expect(onCommand).not.toHaveBeenCalled();
  expect(within(current!).queryByRole("radio", {
    name: "只应用到部分检验项",
  })).toBeNull();
  fireEvent.click(within(current!).getByRole("button", {
    name: "更改处理方式",
  }));
  expect(within(current!).getByRole("radio", {
    name: "只应用到部分检验项",
  })).not.toBeNull();
  fireEvent.click(within(current!).getByRole("radio", {
    name: "应用到系统建议的检验项",
  }));
  expect(within(current!).getByText(
    "这条规则将关联到 2 个检验项；对应 SIP 建议会自动预填。不会立即冻结、编号或生成气泡。",
  )).not.toBeNull();
  fireEvent.click(within(current!).getByRole("button", {
    name: "确认并处理下一条",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
  expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "requirement-matched",
    outcome: "matched_items",
    matched_item_ids: ["dimension-25", "dimension-30"],
  });

  rerender(
    <TechnicalRequirementPanel
      requirements={[
        requirement("requirement-matched", "尺寸规则", {
          match_outcome: "matched_items",
          matched_candidate_ids: ["dimension-25", "dimension-30"],
          review_required: false,
          review_status: "confirmed",
        }),
        requirement("requirement-next", "下一条要求"),
      ]}
      {...props}
    />,
  );
  expect(within(screen.getByText("下一条要求").closest("li")!).getByText(
    "当前处理",
  )).not.toBeNull();
});

test("部分检验项使用可搜索多选，并一次提交完整 target 集合", async () => {
  const onCommand = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("requirement-subset", "未注尺寸公差"),
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
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  const current = screen.getByText("未注尺寸公差").closest("li");
  expect(current).not.toBeNull();
  fireEvent.click(within(current!).getByRole("radio", {
    name: "只应用到部分检验项",
  }));

  const search = within(current!).getByRole("searchbox", {
    name: "搜索检验项",
  });
  fireEvent.change(search, { target: { value: "30" } });
  expect(within(current!).queryByRole("checkbox", { name: "25" })).toBeNull();
  fireEvent.click(within(current!).getByRole("checkbox", { name: "30" }));
  fireEvent.change(search, { target: { value: "" } });
  fireEvent.click(within(current!).getByRole("checkbox", { name: "25" }));
  fireEvent.click(within(current!).getByRole("button", {
    name: "确认并处理下一条",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
  expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "requirement-subset",
    outcome: "matched_items",
    matched_item_ids: ["dimension-25", "dimension-30"],
  });
});

test("终态收敛为只读摘要，并可查看、修改和进入检验项审核", () => {
  const onSelectItem = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("confirmed", "未注尺寸公差", {
          match_outcome: "matched_items",
          matched_candidate_ids: ["dimension-25", "dimension-30"],
          review_required: false,
          review_status: "confirmed",
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
      ]}
      onSelectItem={onSelectItem}
      onCommand={vi.fn()}
    />,
  );

  expect(screen.getByText("已确认 1")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "进入检验项审核" }));
  expect(onSelectItem).toHaveBeenCalledWith("dimension-25");

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  const confirmed = screen.getByText("未注尺寸公差").closest("li");
  expect(confirmed).not.toBeNull();
  expect(within(confirmed!).getByText("已确认")).not.toBeNull();
  expect(within(confirmed!).getByText("已应用到 2 个检验项")).not.toBeNull();
  fireEvent.click(within(confirmed!).getByRole("button", {
    name: "查看关联项",
  }));
  expect(onSelectItem).toHaveBeenLastCalledWith("dimension-25");

  fireEvent.click(within(confirmed!).getByRole("button", { name: "修改" }));
  expect(within(confirmed!).getByText("当前处理")).not.toBeNull();
  expect((within(confirmed!).getByRole("radio", {
    name: "保留当前关联项",
  }) as HTMLInputElement).checked).toBe(true);
  expect(within(confirmed!).getByRole("button", {
    name: "确认修改",
  }).getAttribute("disabled")).toBeNull();
});

test("全局和排除选择只在显式确认后提交", async () => {
  const onCommand = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[requirement("global", "锐边去毛刺", {
        category: "standalone_check",
        subtype: "deburr",
        match_outcome: "global_scope",
        generated_candidate_id: "global-deburr",
        review_status: "suggested",
      })]}
      items={[]}
      onSelectItem={vi.fn()}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  fireEvent.click(screen.getByRole("radio", { name: "作为全局 SIP 要求" }));
  expect(onCommand).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {
    name: "确认并处理下一条",
  }));
  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "global",
    outcome: "global_scope",
  }));
});

test("提交失败保留草稿，取消后才清除 dirty 状态", async () => {
  const onDraftChange = vi.fn();
  const onCommand = vi.fn().mockResolvedValue(false);
  render(
    <TechnicalRequirementPanel
      requirements={[requirement("failed", "未注尺寸公差")]}
      items={[]}
      onSelectItem={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  fireEvent.click(screen.getByRole("radio", {
    name: "作为全局 SIP 要求",
  }));
  await waitFor(() => expect(onDraftChange).toHaveBeenLastCalledWith(true));
  fireEvent.click(screen.getByRole("button", {
    name: "确认并处理下一条",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledOnce());
  expect((screen.getByRole("radio", {
    name: "作为全局 SIP 要求",
  }) as HTMLInputElement).checked).toBe(true);
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  await waitFor(() => expect(onDraftChange).toHaveBeenLastCalledWith(false));
  expect(screen.getByRole("button", {
    name: "请先选择处理方式",
  }).getAttribute("disabled")).not.toBeNull();
});

test("排除要求只在显式确认后提交，disabled 状态禁止形成草稿", async () => {
  const onCommand = vi.fn();
  const onDraftChange = vi.fn();
  const props = {
    requirements: [requirement("excluded", "非本次检验范围")],
    items: [],
    onSelectItem: vi.fn(),
    onCommand,
    onDraftChange,
  };
  const { rerender } = render(
    <TechnicalRequirementPanel {...props} disabled />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  expect(screen.getByRole("radio", {
    name: "排除此要求",
  }).getAttribute("disabled")).not.toBeNull();
  expect(onDraftChange).not.toHaveBeenCalledWith(true);
  expect(onCommand).not.toHaveBeenCalled();

  rerender(<TechnicalRequirementPanel {...props} />);
  fireEvent.click(screen.getByRole("radio", { name: "排除此要求" }));
  expect(onCommand).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", {
    name: "确认并处理下一条",
  }));
  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "set_technical_requirement_match",
    requirement_id: "excluded",
    outcome: "excluded",
  }));
});

test("当前要求存在 dirty 草稿时禁止切换修改其他终态要求", async () => {
  const onDraftChange = vi.fn();
  render(
    <TechnicalRequirementPanel
      requirements={[
        requirement("pending", "当前待确认要求"),
        requirement("confirmed", "其他已确认要求", {
          match_outcome: "global_scope",
          review_required: false,
          review_status: "confirmed",
        }),
      ]}
      items={[]}
      onSelectItem={vi.fn()}
      onCommand={vi.fn()}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
  fireEvent.click(within(screen.getByText("当前待确认要求").closest("li")!)
    .getByRole("radio", { name: "作为全局 SIP 要求" }));
  await waitFor(() => expect(onDraftChange).toHaveBeenLastCalledWith(true));

  expect(within(screen.getByText("其他已确认要求").closest("li")!)
    .getByRole("button", { name: "修改" })
    .getAttribute("disabled")).not.toBeNull();
});
