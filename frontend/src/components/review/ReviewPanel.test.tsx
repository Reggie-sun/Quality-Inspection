import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { CandidateType, ReviewItem } from "../../api/types";
import { ReviewPanel } from "./ReviewPanel";


afterEach(cleanup);

describe("ReviewPanel", () => {
  test("详情标题使用检验项语义身份且不重复原始标注", () => {
    const item: ReviewItem = {
      item_id: "semantic-heading",
      item_type: "linear_dimension",
      raw_text: "48",
      active: true,
    };

    render(
      <ReviewPanel
        items={[item]}
        onCommand={vi.fn()}
        selectedItemId={item.item_id}
        selectedItemPresentation={{
          displayNumber: 2,
          numberKind: "candidate",
          numberLabel: "候选序号 2",
          typeLabel: "线性尺寸",
          page: 1,
          pageLabel: "第 1 页",
          status: "pending",
          statusLabel: "待审核",
        }}
      />,
    );

    expect(screen.getByRole("article", {
      name: "检验项 2 · 线性尺寸",
    })).not.toBeNull();
    expect(screen.getByRole("heading", {
      name: "检验项 2 · 线性尺寸",
    })).not.toBeNull();
    expect(screen.getByText("候选序号 2")).not.toBeNull();
    expect(screen.queryByRole("heading", { name: "48" })).toBeNull();
    expect(screen.getByLabelText("识别原文：48").textContent).toBe("48");
  });

  test("缺少 presentation 时不伪造所选检验项状态", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "missing-presentation",
          item_type: "thread",
          raw_text: "M8",
          status: "kept",
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="missing-presentation"
      />,
    );

    expect(screen.getByRole("article", {
      name: "检验项 — · —",
    })).not.toBeNull();
    expect(screen.queryByText("待审核")).toBeNull();
  });

  test("原文与基本尺寸相同时不重复显示图纸原文", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "grouped-typed-item",
          item_type: "linear_dimension",
          raw_text: "48",
          nominal: "48",
          upper_tolerance: "0.02",
          lower_tolerance: "-0.01",
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="grouped-typed-item"
      />,
    );

    const parsedResult = screen.getByRole("group", { name: "解析结果" });

    expect(screen.queryByRole("group", { name: "图纸原文" })).toBeNull();
    expect(screen.queryByRole("textbox", {
      name: "原始标注：48",
    })).toBeNull();
    expect(within(parsedResult).getByRole("textbox", {
      name: "基本尺寸：48",
    })).not.toBeNull();
    expect(within(parsedResult).getByRole("textbox", {
      name: "上公差：48",
    })).not.toBeNull();
    expect(within(parsedResult).getByRole("textbox", {
      name: "下公差：48",
    })).not.toBeNull();
    expect(within(parsedResult).queryByRole("textbox", {
      name: "原始标注：48",
    })).toBeNull();
  });

  test("原文与解析结果不同时仅显示只读识别原文", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "different-source-item",
          item_type: "linear_dimension",
          raw_text: "48 ±0.02",
          nominal: "48",
          upper_tolerance: "0.02",
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="different-source-item"
      />,
    );

    const drawingSource = screen.getByRole("group", { name: "图纸原文" });
    const sourceReference = within(drawingSource).getByLabelText(
      "识别原文：48 ±0.02",
    );

    expect(sourceReference.textContent).toBe("48 ±0.02");
    expect(within(drawingSource).queryByRole("textbox")).toBeNull();
  });

  test("待确认项目即使原文与解析结果相同也显示只读识别原文", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "confirmation-source-item",
          item_type: "linear_dimension",
          raw_text: "48",
          nominal: "48",
          requires_confirmation: true,
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="confirmation-source-item"
      />,
    );

    const drawingSource = screen.getByRole("group", { name: "图纸原文" });
    expect(within(drawingSource).getByLabelText(
      "识别原文：48",
    ).textContent).toBe("48");
    expect(within(drawingSource).queryByRole("textbox")).toBeNull();
  });

  test("复杂检验项只读展示识别原文且不渲染空解析分组", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "grouped-complex-item",
          raw_text: "Ra 3.2",
          coordinates: [9, 10, 11, 12],
          coarse_type: "roughness",
          requires_confirmation: true,
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="grouped-complex-item"
      />,
    );

    const drawingSource = screen.getByRole("group", { name: "图纸原文" });

    expect(within(drawingSource).getByLabelText(
      "识别原文：Ra 3.2",
    ).textContent).toBe("Ra 3.2");
    expect(within(drawingSource).queryByRole("textbox", {
      name: "原始标注：Ra 3.2",
    })).toBeNull();
    expect(within(drawingSource).getByRole("textbox", {
      name: "坐标：Ra 3.2",
    })).not.toBeNull();
    expect(within(drawingSource).getByRole("combobox", {
      name: "粗分类：Ra 3.2",
    })).not.toBeNull();
    const requiresConfirmation = within(drawingSource).getByRole("checkbox", {
      name: "需要人工确认：Ra 3.2",
    });
    expect(requiresConfirmation.closest("label")?.classList.contains(
      "review-field-group__confirmation",
    )).toBe(true);
    expect(screen.queryByRole("group", { name: "解析结果" })).toBeNull();
  });

  test("P0-UI-006 keeps merge out of details and exposes seven single-item command types", () => {
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
    expect(screen.queryByText("选择需要合并的检验项")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "合并所选检验项" }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));
    fireEvent.click(screen.getByRole("button", { name: "排除检验项：M6" }));
    fireEvent.click(screen.getByRole("button", { name: "确认排除" }));
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
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10 ±0.02" }));
    fireEvent.change(screen.getByLabelText("基本尺寸：10 ±0.02"), {
      target: { value: "12.50" },
    });
    fireEvent.change(screen.getByLabelText("上公差：10 ±0.02"), {
      target: { value: "0.03" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "修改保存检验项：10 ±0.02" }),
    );

    rerender(
      <ReviewPanel items={items} onCommand={onCommand} selectedItemId="complex-1" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：Ra 3.2" }));
    fireEvent.change(screen.getByLabelText("坐标：Ra 3.2"), {
      target: { value: "11,12,13,14" },
    });
    fireEvent.change(screen.getByLabelText("粗分类：Ra 3.2"), {
      target: { value: "weld" },
    });
    fireEvent.click(screen.getByLabelText("需要人工确认：Ra 3.2"));
    fireEvent.click(
      screen.getByRole("button", { name: "修改保存检验项：Ra 3.2" }),
    );
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
        raw_text: "10 ±0.02",
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
        raw_text: "Ra 3.2",
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

  test("操作栏按业务语义分组并常驻解释排除与无需气泡的后果", () => {
    render(
      <ReviewPanel
        items={[{
          item_id: "semantic-actions",
          item_type: "linear_dimension",
          raw_text: "20",
          balloon_required: true,
          active: true,
        }]}
        onCommand={vi.fn()}
        selectedItemId="semantic-actions"
      />,
    );

    const decisionGroup = screen.getByRole("group", { name: "检验结论" });
    const balloonGroup = screen.getByRole("group", { name: "气泡标记" });
    const commandRail = screen.getByRole("complementary", {
      name: "检验项操作",
    });

    expect(commandRail.classList.contains("review-command-rail--flat")).toBe(true);
    expect(within(decisionGroup).getByText(
      "不进入 SIP，也不生成气泡",
    )).not.toBeNull();
    expect(within(balloonGroup).getByText(
      "仍进入 SIP，仅不生成图纸气泡",
    )).not.toBeNull();
    expect(within(decisionGroup).getByRole("button", {
      name: "排除检验项：20",
    })).not.toBeNull();
    expect(within(balloonGroup).getByRole("button", {
      name: "设为无需气泡：20",
    })).not.toBeNull();
  });

  test("排除需要行内确认且取消、失败、重试与 Escape 不会误提交", async () => {
    const onCommand = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const item: ReviewItem = {
      item_id: "exclude-confirmation",
      item_type: "linear_dimension",
      raw_text: "25",
      balloon_required: true,
      active: true,
    };

    render(
      <ReviewPanel
        items={[item]}
        onCommand={onCommand}
        selectedItemId={item.item_id}
      />,
    );

    const exclude = screen.getByRole("button", {
      name: "排除检验项：25",
    });

    fireEvent.click(exclude);
    expect(onCommand).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", {
      name: "确认排除这条检验项？",
    })).not.toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "取消排除" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "取消排除" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(onCommand).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(exclude);

    fireEvent.click(exclude);
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(onCommand).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(exclude);

    fireEvent.click(exclude);
    fireEvent.click(screen.getByRole("button", { name: "确认排除" }));
    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
    expect(onCommand).toHaveBeenLastCalledWith({
      type: "exclude",
      item_id: item.item_id,
    });
    expect(screen.getByRole("alertdialog")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "确认排除" }));
    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  test("所选检验项仅通过解析字段进入修改且只在草稿有差异时允许保存", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const { rerender } = render(
      <ReviewPanel
        items={[{
          item_id: "edit-item",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "10",
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="edit-item"
      />,
    );

    const nominal = screen.getByRole("textbox", { name: "基本尺寸：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );

    expect(screen.queryByRole("textbox", {
      name: "原始标注：10",
    })).toBeNull();
    expect(nominal.hasAttribute("disabled")).toBe(false);
    expect(nominal.hasAttribute("readonly")).toBe(true);
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.focus(nominal);
    expect(nominal.hasAttribute("readonly")).toBe(false);
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.change(nominal, { target: { value: "11" } });
    expect(save.hasAttribute("disabled")).toBe(false);
    fireEvent.change(nominal, { target: { value: "10" } });
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.change(nominal, { target: { value: "11" } });
    fireEvent.click(save);

    expect(onCommand).toHaveBeenCalledWith({
      type: "edit",
      item_id: "edit-item",
      fields: {
        raw_text: "10",
        nominal: "11",
      },
    });
    rerender(
      <ReviewPanel
        items={[{
          item_id: "edit-item",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "11",
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="edit-item"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect(nominal.hasAttribute("readonly")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
    expect((nominal as HTMLInputElement).value).toBe("11");
    expect(save.hasAttribute("disabled")).toBe(true);
  });

  test("修改成功后采用服务端规范化的数量值", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const { rerender } = render(
      <ReviewPanel
        items={[{
          item_id: "canonical-quantity",
          item_type: "linear_dimension",
          raw_text: "尺寸",
          quantity: 2,
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="canonical-quantity"
      />,
    );

    const quantity = screen.getByRole("spinbutton", { name: "数量：尺寸" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：尺寸" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：尺寸" }));
    fireEvent.change(quantity, { target: { value: "01" } });
    expect(save.hasAttribute("disabled")).toBe(false);
    fireEvent.click(save);

    rerender(
      <ReviewPanel
        items={[{
          item_id: "canonical-quantity",
          item_type: "linear_dimension",
          raw_text: "尺寸",
          quantity: 1,
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="canonical-quantity"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect((quantity as HTMLInputElement).value).toBe("1");
      expect(quantity.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
  });

  test("持久化签名不变的新快照仍会规范化数量值", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const items: ReviewItem[] = [{
      item_id: "same-signature-quantity",
      item_type: "linear_dimension",
      raw_text: "数量尺寸",
      quantity: 2,
      active: true,
    }];
    const { rerender } = render(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="same-signature-quantity"
      />,
    );

    const quantity = screen.getByRole(
      "spinbutton",
      { name: "数量：数量尺寸" },
    );
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：数量尺寸" },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：数量尺寸" }),
    );
    fireEvent.change(quantity, { target: { value: "02" } });
    fireEvent.click(save);

    rerender(
      <ReviewPanel
        items={items.map((item) => ({ ...item }))}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="same-signature-quantity"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect((quantity as HTMLInputElement).value).toBe("2");
      expect(quantity.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });

    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：数量尺寸" }),
    );
    fireEvent.change(quantity, { target: { value: "02" } });
    fireEvent.click(save);
    await act(async () => resolveCommand(true));
    await waitFor(() => {
      expect((quantity as HTMLInputElement).value).toBe("02");
      expect(quantity.hasAttribute("readonly")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });

    rerender(
      <ReviewPanel
        items={items.map((item) => ({ ...item }))}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="same-signature-quantity"
      />,
    );
    await waitFor(() => {
      expect((quantity as HTMLInputElement).value).toBe("2");
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
  });

  test("修改成功后采用服务端规范化的复杂检验项坐标", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const { rerender } = render(
      <ReviewPanel
        items={[{
          item_id: "canonical-coordinates",
          raw_text: "位置度",
          coordinates: [0, 0, 0, 0],
          coarse_type: "geometric_tolerance",
          requires_confirmation: false,
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="canonical-coordinates"
      />,
    );

    const coordinates = screen.getByRole("textbox", { name: "坐标：位置度" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：位置度" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：位置度" }));
    fireEvent.change(coordinates, { target: { value: "1, 2, 3, 4" } });
    fireEvent.click(save);

    rerender(
      <ReviewPanel
        items={[{
          item_id: "canonical-coordinates",
          raw_text: "位置度",
          coordinates: [1, 2, 3, 4],
          coarse_type: "geometric_tolerance",
          requires_confirmation: false,
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="canonical-coordinates"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect((coordinates as HTMLInputElement).value).toBe("1,2,3,4");
      expect(coordinates.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
  });

  test("持久化签名不变的新快照仍会规范化复杂检验项坐标", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const items: ReviewItem[] = [{
      item_id: "same-signature-coordinates",
      raw_text: "同值位置度",
      coordinates: [1, 2, 3, 4],
      coarse_type: "geometric_tolerance",
      requires_confirmation: false,
      active: true,
    }];
    const { rerender } = render(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="same-signature-coordinates"
      />,
    );

    const coordinates = screen.getByRole(
      "textbox",
      { name: "坐标：同值位置度" },
    );
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：同值位置度" },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：同值位置度" }),
    );
    fireEvent.change(coordinates, { target: { value: "1, 2, 3, 4" } });
    fireEvent.click(save);

    rerender(
      <ReviewPanel
        items={items.map((item) => ({ ...item }))}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="same-signature-coordinates"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect((coordinates as HTMLInputElement).value).toBe("1,2,3,4");
      expect(coordinates.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
  });

  test("成功确认并刷新后继续采用同一检验项的后续服务端更新", async () => {
    let resolveCommand: (outcome: boolean) => void = () => undefined;
    const onCommand = vi.fn(() => new Promise<boolean>((resolve) => {
      resolveCommand = resolve;
    }));
    const onDraftChange = vi.fn();
    const renderPanel = (nominal: string) => (
      <ReviewPanel
        items={[{
          item_id: "later-server-update",
          item_type: "linear_dimension",
          raw_text: "服务器原值",
          nominal,
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="later-server-update"
      />
    );
    const { rerender } = render(renderPanel("10"));

    const nominal = screen.getByRole(
      "textbox",
      { name: "基本尺寸：服务器原值" },
    );
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：服务器原值" },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：服务器原值" }),
    );
    fireEvent.change(nominal, { target: { value: "11" } });
    fireEvent.click(save);

    rerender(renderPanel("11"));
    await act(async () => resolveCommand(true));
    await waitFor(() => {
      expect((nominal as HTMLInputElement).value).toBe("11");
      expect(nominal.hasAttribute("readonly")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });

    rerender(renderPanel("12"));

    await waitFor(() => {
      expect((nominal as HTMLInputElement).value).toBe("12");
      expect(nominal.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
  });

  test("void 修改命令成功后保留提交值并清理本地草稿", async () => {
    const onCommand = vi.fn();
    const onDraftChange = vi.fn();
    const items: ReviewItem[] = [{
      item_id: "void-edit-item",
      item_type: "linear_dimension",
      raw_text: "10",
      nominal: "10",
      active: true,
    }];
    const renderPanel = () => (
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="void-edit-item"
      />
    );
    const { rerender } = render(renderPanel());

    const nominal = screen.getByRole("textbox", { name: "基本尺寸：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(nominal, { target: { value: "11" } });
    expect(onDraftChange).toHaveBeenLastCalledWith(true);

    fireEvent.click(save);

    await waitFor(() => {
      expect(onCommand).toHaveBeenCalledTimes(1);
      expect(nominal.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
    expect((nominal as HTMLInputElement).value).toBe("11");

    rerender(renderPanel());
    expect((nominal as HTMLInputElement).value).toBe("11");
    expect(save.hasAttribute("disabled")).toBe(true);
    expect(onDraftChange).toHaveBeenLastCalledWith(false);

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(nominal, { target: { value: "10" } });
    expect((nominal as HTMLInputElement).value).toBe("10");
    expect(save.hasAttribute("disabled")).toBe(false);
    expect(onDraftChange).toHaveBeenLastCalledWith(true);

    fireEvent.change(nominal, { target: { value: "11" } });
    expect(save.hasAttribute("disabled")).toBe(true);
    expect(onDraftChange).toHaveBeenLastCalledWith(false);
  });

  test("切换所选检验项会结束原检验项的编辑模式", () => {
    const items: ReviewItem[] = [
      {
        item_id: "item-a",
        item_type: "linear_dimension",
        raw_text: "A",
        nominal: "10",
        active: true,
      },
      {
        item_id: "item-b",
        item_type: "linear_dimension",
        raw_text: "B",
        nominal: "20",
        active: true,
      },
    ];
    const onCommand = vi.fn();
    const { rerender } = render(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        selectedItemId="item-a"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：A" }));
    expect(
      screen.getByRole("textbox", { name: "基本尺寸：A" })
        .hasAttribute("readonly"),
    ).toBe(false);

    rerender(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        selectedItemId="item-b"
      />,
    );
    expect(
      screen.getByRole("textbox", { name: "基本尺寸：B" })
        .hasAttribute("readonly"),
    ).toBe(true);

    rerender(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        selectedItemId="item-a"
      />,
    );
    const nominal = screen.getByRole("textbox", { name: "基本尺寸：A" });
    expect(nominal.hasAttribute("readonly")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：A" }));
    expect(nominal.hasAttribute("readonly")).toBe(false);
  });

  test("修改命令显式失败时保留本地草稿和编辑模式", async () => {
    const onCommand = vi.fn().mockResolvedValue(false);
    render(
      <ReviewPanel
        items={[{
          item_id: "failed-edit-item",
          item_type: "linear_dimension",
          raw_text: "10",
          nominal: "10",
          active: true,
        }]}
        onCommand={onCommand}
        selectedItemId="failed-edit-item"
      />,
    );

    const nominal = screen.getByRole("textbox", { name: "基本尺寸：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(nominal, { target: { value: "11" } });
    fireEvent.click(save);

    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
    expect((nominal as HTMLInputElement).value).toBe("11");
    expect(nominal.hasAttribute("disabled")).toBe(false);
    expect(save.hasAttribute("disabled")).toBe(false);
  });

  test("新增和拆分草稿仅在命令成功后重置", async () => {
    const onCommand = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(
      <ReviewPanel
        items={[{
          item_id: "split-item",
          item_type: "thread",
          raw_text: "M8 深10",
          active: true,
        }]}
        onCommand={onCommand}
        selectedItemId="split-item"
      />,
    );

    const manualRawText = screen.getByLabelText("新增检验项原始标注");
    const manualCoordinates = screen.getByLabelText("新增检验项坐标");
    fireEvent.change(manualRawText, { target: { value: "M10" } });
    fireEvent.change(manualCoordinates, { target: { value: "1,2,3,4" } });
    fireEvent.click(screen.getByRole("button", { name: "新增检验项" }));

    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
    expect((manualRawText as HTMLInputElement).value).toBe("M10");
    expect((manualCoordinates as HTMLInputElement).value).toBe("1,2,3,4");

    fireEvent.click(screen.getByRole("button", { name: "新增检验项" }));
    await waitFor(() => {
      expect(onCommand).toHaveBeenCalledTimes(2);
      expect((manualRawText as HTMLInputElement).value).toBe("");
    });
    expect((manualCoordinates as HTMLInputElement).value).toBe("");

    const splitDraft = screen.getByLabelText("拆分内容：M8 深10");
    fireEvent.change(splitDraft, { target: { value: "M8|深10" } });
    fireEvent.click(
      screen.getByRole("button", { name: "拆分检验项：M8 深10" }),
    );

    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(3));
    expect((splitDraft as HTMLInputElement).value).toBe("M8|深10");

    fireEvent.click(
      screen.getByRole("button", { name: "拆分检验项：M8 深10" }),
    );
    await waitFor(() => {
      expect(onCommand).toHaveBeenCalledTimes(4);
      expect((splitDraft as HTMLInputElement).value).toBe("");
    });
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
    expect(screen.getByRole("heading", { level: 3 }).textContent)
      .not.toContain("尺寸 157");
    expect(screen.getByLabelText("识别原文：尺寸 157").textContent)
      .toBe("尺寸 157");
    expect(screen.queryAllByLabelText(/^原始标注：/)).toHaveLength(0);

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

    expect(screen.getByRole("heading", { level: 3 }).textContent)
      .not.toContain("新型标注");
    expect(screen.getByLabelText("识别原文：新型标注").textContent)
      .toBe("新型标注");
    expect(document.body.textContent).not.toContain("future_network_type");
    expect(screen.getByRole("button", { name: "保留检验项：新型标注" }))
      .not.toBeNull();
    expect(screen.getByRole("button", { name: "排除检验项：新型标注" }))
      .not.toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：新型标注" }),
    );
    expect(screen.getByRole("button", {
      name: "修改保存检验项：新型标注",
    }).hasAttribute("disabled")).toBe(true);
    expect(onCommand).not.toHaveBeenCalled();
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

    expect(screen.queryByRole("textbox", { name: "原始标注：10" }))
      .toBeNull();
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
