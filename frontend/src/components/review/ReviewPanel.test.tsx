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
    expect(screen.getAllByDisplayValue("48")).toHaveLength(1);
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

  test("将图纸原文与类型化解析结果放入独立语义分组", () => {
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

    const drawingSource = screen.getByRole("group", { name: "图纸原文" });
    const parsedResult = screen.getByRole("group", { name: "解析结果" });

    const rawText = within(drawingSource).getByRole("textbox", {
      name: "原始标注：48",
    });
    expect(rawText.closest("label")?.classList.contains(
      "review-field-group__confirmation",
    )).toBe(false);
    expect(within(drawingSource).queryByRole("textbox", {
      name: "基本尺寸：48",
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

  test("将复杂检验项的来源字段放入图纸原文且不渲染空解析分组", () => {
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

    expect(within(drawingSource).getByRole("textbox", {
      name: "原始标注：Ra 3.2",
    })).not.toBeNull();
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
    fireEvent.change(screen.getByLabelText("原始标注：10 ±0.02"), {
      target: { value: "12.50 +0.03" },
    });
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

  test("所选检验项默认只读，聚焦字段可进入修改且仅在草稿有差异时允许保存", async () => {
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

    const rawText = screen.getByRole("textbox", { name: "原始标注：10" });
    const nominal = screen.getByRole("textbox", { name: "基本尺寸：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );

    expect(rawText.hasAttribute("disabled")).toBe(false);
    expect(rawText.hasAttribute("readonly")).toBe(true);
    expect(nominal.hasAttribute("disabled")).toBe(false);
    expect(nominal.hasAttribute("readonly")).toBe(true);
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.focus(nominal);
    expect(rawText.hasAttribute("readonly")).toBe(false);
    expect(nominal.hasAttribute("readonly")).toBe(false);
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.change(rawText, { target: { value: "11" } });
    expect(save.hasAttribute("disabled")).toBe(false);
    fireEvent.change(rawText, { target: { value: "10" } });
    expect(save.hasAttribute("disabled")).toBe(true);

    fireEvent.change(rawText, { target: { value: "11" } });
    fireEvent.click(save);

    expect(onCommand).toHaveBeenCalledWith({
      type: "edit",
      item_id: "edit-item",
      fields: {
        raw_text: "11",
        nominal: "10",
      },
    });
    rerender(
      <ReviewPanel
        items={[{
          item_id: "edit-item",
          item_type: "linear_dimension",
          raw_text: "11",
          nominal: "10",
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="edit-item"
      />,
    );
    await act(async () => resolveCommand(true));

    await waitFor(() => {
      expect(rawText.hasAttribute("readonly")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
    expect((rawText as HTMLInputElement).value).toBe("11");
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
    const renderPanel = (rawText: string) => (
      <ReviewPanel
        items={[{
          item_id: "later-server-update",
          item_type: "linear_dimension",
          raw_text: rawText,
          nominal: "10",
          active: true,
        }]}
        onCommand={onCommand}
        onDraftChange={onDraftChange}
        selectedItemId="later-server-update"
      />
    );
    const { rerender } = render(renderPanel("服务器原值"));

    const rawText = screen.getByRole(
      "textbox",
      { name: "原始标注：服务器原值" },
    );
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：服务器原值" },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：服务器原值" }),
    );
    fireEvent.change(rawText, { target: { value: "保存后" } });
    fireEvent.click(save);

    rerender(renderPanel("保存后"));
    await act(async () => resolveCommand(true));
    await waitFor(() => {
      expect((rawText as HTMLInputElement).value).toBe("保存后");
      expect(rawText.hasAttribute("readonly")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });

    rerender(renderPanel("服务器后续更新"));

    await waitFor(() => {
      expect((rawText as HTMLInputElement).value).toBe("服务器后续更新");
      expect(rawText.hasAttribute("readonly")).toBe(true);
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

    const rawText = screen.getByRole("textbox", { name: "原始标注：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(rawText, { target: { value: "11" } });
    expect(onDraftChange).toHaveBeenLastCalledWith(true);

    fireEvent.click(save);

    await waitFor(() => {
      expect(onCommand).toHaveBeenCalledTimes(1);
      expect(rawText.hasAttribute("readonly")).toBe(true);
      expect(save.hasAttribute("disabled")).toBe(true);
      expect(onDraftChange).toHaveBeenLastCalledWith(false);
    });
    expect((rawText as HTMLInputElement).value).toBe("11");

    rerender(renderPanel());
    expect((rawText as HTMLInputElement).value).toBe("11");
    expect(save.hasAttribute("disabled")).toBe(true);
    expect(onDraftChange).toHaveBeenLastCalledWith(false);

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(rawText, { target: { value: "10" } });
    expect((rawText as HTMLInputElement).value).toBe("10");
    expect(save.hasAttribute("disabled")).toBe(false);
    expect(onDraftChange).toHaveBeenLastCalledWith(true);

    fireEvent.change(rawText, { target: { value: "11" } });
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
      screen.getByRole("textbox", { name: "原始标注：A" })
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
      screen.getByRole("textbox", { name: "原始标注：B" })
        .hasAttribute("readonly"),
    ).toBe(true);

    rerender(
      <ReviewPanel
        items={items}
        onCommand={onCommand}
        selectedItemId="item-a"
      />,
    );
    const rawText = screen.getByRole("textbox", { name: "原始标注：A" });
    expect(rawText.hasAttribute("readonly")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：A" }));
    expect(rawText.hasAttribute("readonly")).toBe(false);
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

    const rawText = screen.getByRole("textbox", { name: "原始标注：10" });
    const save = screen.getByRole(
      "button",
      { name: "修改保存检验项：10" },
    );
    fireEvent.click(screen.getByRole("button", { name: "修改检验项：10" }));
    fireEvent.change(rawText, { target: { value: "11" } });
    fireEvent.click(save);

    await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
    expect((rawText as HTMLInputElement).value).toBe("11");
    expect(rawText.hasAttribute("disabled")).toBe(false);
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
    expect(screen.getByRole("article").textContent).not.toContain("尺寸 157");
    expect(screen.getByDisplayValue("尺寸 157")).not.toBeNull();
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

    expect(screen.getByRole("article").textContent).not.toContain("新型标注");
    expect(screen.getByDisplayValue("新型标注")).not.toBeNull();
    expect(document.body.textContent).not.toContain("future_network_type");
    expect(screen.getByRole("button", { name: "保留检验项：新型标注" }))
      .not.toBeNull();
    expect(screen.getByRole("button", { name: "排除检验项：新型标注" }))
      .not.toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "修改检验项：新型标注" }),
    );
    fireEvent.change(screen.getByLabelText("原始标注：新型标注"), {
      target: { value: "新型标注（修改）" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "修改保存检验项：新型标注" }),
    );

    expect(onCommand).toHaveBeenCalledWith({
      type: "edit",
      item_id: "future-item",
      fields: { raw_text: "新型标注（修改）" },
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
