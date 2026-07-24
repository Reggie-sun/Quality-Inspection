import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { CandidateType, ReviewItem } from "../../api/types";
import { ReviewPanel } from "./ReviewPanel";


afterEach(cleanup);

describe("ReviewPanel", () => {
  test("P0-UI-006 exposes all eight review commands only on explicit actions", () => {
    const onCommand = vi.fn();
    const items: ReviewItem[] = [
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
    ];
    const { rerender } = render(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        selectedItemId="i1"
      />,
    );

    expect(onCommand).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("选择需要合并的检验项"));
    fireEvent.click(screen.getByLabelText("选择检验项 1：M6"));
    fireEvent.click(screen.getByLabelText("选择检验项 2：M6 通"));
    fireEvent.click(screen.getByRole("button", { name: "合并所选检验项" }));
    fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));
    fireEvent.click(screen.getByRole("button", { name: "排除检验项：M6" }));
    fireEvent.change(screen.getByLabelText("拆分内容：M6"), {
      target: { value: "M6|深10" },
    });
    fireEvent.click(screen.getByRole("button", { name: "拆分检验项：M6" }));
    fireEvent.click(
      screen.getByRole("button", { name: "设为无需气泡：M6" }),
    );

    rerender(
      <ReviewPanel items={items} onCommand={onCommand} selectedItemId="i2" />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "设为需要气泡：M6 通" }),
    );

    rerender(
      <ReviewPanel items={items} onCommand={onCommand} selectedItemId="typed-1" />,
    );
    fireEvent.change(screen.getByLabelText("原始标注：10 ±0.02"), {
      target: { value: "12.50 +0.03" },
    });
    fireEvent.change(screen.getByLabelText("基本尺寸：10 ±0.02"), {
      target: { value: "12.50" },
    });
    fireEvent.change(screen.getByLabelText("上公差：10 ±0.02"), {
      target: { value: "0.03" },
    });
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10 ±0.02" }));

    rerender(
      <ReviewPanel items={items} onCommand={onCommand} selectedItemId="complex-1" />,
    );
    fireEvent.change(screen.getByLabelText("原始标注：Ra 3.2"), {
      target: { value: "Ra 1.6" },
    });
    fireEvent.change(screen.getByLabelText("坐标：Ra 3.2"), {
      target: { value: "11,12,13,14" },
    });
    fireEvent.change(screen.getByLabelText("粗分类：Ra 3.2"), {
      target: { value: "weld" },
    });
    fireEvent.click(screen.getByLabelText("需要人工确认：Ra 3.2"));
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：Ra 3.2" }));
    fireEvent.click(
      screen.getByRole("button", { name: "确认候选项：Ra 3.2" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "拒绝候选项：Ra 3.2" }),
    );

    fireEvent.change(screen.getByLabelText("新增检验项原始标注"), {
      target: { value: "M8" },
    });
    fireEvent.change(screen.getByLabelText("新增检验项坐标"), {
      target: { value: "10,20,30,40" },
    });
    fireEvent.change(screen.getByLabelText("新增检验项类型"), {
      target: { value: "diameter_dimension" },
    });
    fireEvent.click(screen.getByLabelText("新增检验项需要气泡"));
    fireEvent.click(screen.getByRole("button", { name: "新增检验项" }));
    expect(screen.getByLabelText("新增检验项坐标").getAttribute("placeholder"))
      .toBe("例如：10, 20, 30, 40");

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

  test("大量检验项只渲染所选 active item 的完整详情表单", () => {
    const items: ReviewItem[] = Array.from({ length: 200 }, (_, index) => ({
      item_id: `item-${index + 1}`,
      item_type: "linear_dimension",
      raw_text: `尺寸 ${index + 1}`,
      active: true,
    }));
    const { rerender } = render(
      <ReviewPanel
        items={items}
        onCommand={vi.fn()}
        selectedItemId="item-157"
      />,
    );

    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article").textContent).toContain("尺寸 157");
    expect(screen.getAllByLabelText(/^原始标注：/)).toHaveLength(1);

    rerender(<ReviewPanel items={items} onCommand={vi.fn()} />);
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(screen.getByText("请先从检验项列表选择一项。")).not.toBeNull();
  });

  test("所选检验项将字段、操作和拆分区分成独立工作区", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "layout-item",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "10",
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="layout-item"
      />,
    );

    const item = screen.getByRole("article");
    expect(item.querySelector(".review-selected-item__form")).not.toBeNull();
    expect(item.querySelector(".review-command-rail")).not.toBeNull();
    expect(item.querySelector(".review-split-row")).not.toBeNull();
  });

  test("未来 item_type 安全降级且审核命令仍可用", () => {
    const onCommand = vi.fn();
    const item: ReviewItem = {
      item_id: "future-item",
      item_type: "future_network_type" as unknown as CandidateType,
      raw_text: "新型标注",
      balloon_required: true,
      active: true,
    };

    expect(() => render(
      <ReviewPanel
        items={[item]}
        onCommand={onCommand}
        selectedItemId="future-item"
      />,
    )).not.toThrow();

    expect(screen.getByRole("article").textContent).toContain("新型标注");
    expect(document.body.textContent).not.toContain("future_network_type");
    expect(screen.getByRole("button", { name: "保留检验项：新型标注" }))
      .not.toBeNull();
    expect(screen.getByRole("button", { name: "排除检验项：新型标注" }))
      .not.toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：新型标注" }),
    );

    expect(onCommand).toHaveBeenCalledWith({
      type: "edit",
      item_id: "future-item",
      fields: { raw_text: "新型标注" },
    });
  });

  test("审核冻结后详情草稿字段不可继续编辑", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "frozen-item",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "10",
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="frozen-item"
        disabled
      />,
    );

    expect(screen.getByRole("textbox", { name: "原始标注：10" })
      .hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("textbox", { name: "基本尺寸：10" })
      .hasAttribute("disabled")).toBe(true);
  });

  test("取消新增检验项会清空草稿并恢复已保存状态", () => {
    const onDraftChange = vi.fn();
    render(
      <ReviewPanel
        items={[]}
        onCommand={vi.fn()}
        onDraftChange={onDraftChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("新增检验项原始标注"), {
      target: { value: "M8" },
    });
    fireEvent.change(screen.getByLabelText("新增检验项坐标"), {
      target: { value: "10,20,30,40" },
    });
    expect(onDraftChange).toHaveBeenLastCalledWith(true);

    fireEvent.click(screen.getByRole("button", { name: "取消新增检验项" }));

    expect(
      (screen.getByLabelText("新增检验项原始标注") as HTMLInputElement).value,
    ).toBe("");
    expect(
      (screen.getByLabelText("新增检验项坐标") as HTMLInputElement).value,
    ).toBe("");
    expect(onDraftChange).toHaveBeenLastCalledWith(false);
  });
});
