import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { InspectionItemTable } from "./InspectionItemTable";


const originalScrollIntoView = Object.getOwnPropertyDescriptor(
  Element.prototype,
  "scrollIntoView",
);

afterEach(() => {
  cleanup();
  if (originalScrollIntoView === undefined) {
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  } else {
    Object.defineProperty(
      Element.prototype,
      "scrollIntoView",
      originalScrollIntoView,
    );
  }
});

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
  expect(row.textContent).toContain("线性尺寸");
  expect(row.textContent).toContain("10");
  expect(row.textContent).toContain("+0.02 / -0.02");
  expect(row.textContent).toContain("第 1 页");
  expect(row.textContent).toContain("需人工处理");
  expect(row.textContent).toContain("存在保护区重叠");
  expect(document.body.textContent).not.toContain("i1");
  expect(document.body.textContent).not.toContain("i2");

  fireEvent.click(screen.getByRole("row", { name: /M8/ }));
  expect(onSelectItem).toHaveBeenCalledWith("i2");

  rerender(<InspectionItemTable {...props} selectedItemId="i2" />);
  expect(screen.getByRole("row", { name: /M8/ }).getAttribute("data-selected"))
    .toBe("true");
  expect(screen.getByRole("row", { name: /10 ±0.02/ }).getAttribute("data-selected"))
    .toBe("false");
});

test("compact 模式只保留序号、检验项和状态三列", () => {
  render(
    <InspectionItemTable
      compact
      items={[{
        item_id: "compact-item",
        raw_text: "M8",
        item_type: "thread",
        page_index: 0,
        status: "kept",
        active: true,
      }]}
      balloons={[]}
      pendingSources={[{
        observationId: "compact-observation",
        sourceId: "compact-source",
        rawText: "去除毛刺",
        coordinates: [1, 2, 3, 4],
        pageIndex: 1,
      }]}
      filter="all"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
    />,
  );

  const table = screen.getByRole("table", { name: "检验项列表" });
  expect(
    within(table).getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["序号", "检验项", "状态"]);
  expect(
    within(screen.getByRole("row", { name: /M8/ })).getAllByRole("cell"),
  ).toHaveLength(3);
  expect(
    within(screen.getByRole("row", { name: /去除毛刺/ })).getAllByRole("cell"),
  ).toHaveLength(3);
});

test("列表不显示搜索框并保留状态筛选和紧凑分页", () => {
  const items = Array.from({ length: 51 }, (_, index) => ({
    item_id: `internal-${index}`,
    raw_text: `检验标注 ${index + 1}`,
    item_type: "linear_dimension" as const,
    page_index: 0,
    status: index % 2 === 0 ? "kept" : "pending",
    active: true,
  }));
  render(
    <InspectionItemTable
      items={items}
      balloons={[]}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "下一页" })).not.toBeNull();
  expect(screen.getByText("第 1 / 2 页")).not.toBeNull();
  expect(screen.queryByRole("searchbox", { name: "搜索检验项" })).toBeNull();
  expect(screen.getByRole("combobox", { name: "筛选状态" })).not.toBeNull();
});

test("紧凑分页只在 DOM 渲染当前页检验项", () => {
  const items = Array.from({ length: 51 }, (_, index) => ({
    item_id: `internal-${index}`,
    raw_text: `检验标注 ${index + 1}`,
    item_type: "linear_dimension" as const,
    page_index: 0,
    active: true,
  }));
  const { container } = render(
    <InspectionItemTable
      items={items}
      balloons={[]}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  expect(container.querySelectorAll("[role='row'][data-item-id]")).toHaveLength(50);
  expect(container.querySelector("[data-item-id='internal-50']")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "下一页" }));

  expect(screen.getByText("第 2 / 2 页")).not.toBeNull();
  expect(container.querySelectorAll("[role='row'][data-item-id]")).toHaveLength(1);
  expect(screen.getByRole("row", { name: /检验标注 51/ })).not.toBeNull();
});

test("外部选择第 51 项时自动跳到第二页并将选中行滚入视野", async () => {
  const scrollIntoView = vi.fn();
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  const items = Array.from({ length: 51 }, (_, index) => ({
    item_id: `internal-${index}`,
    raw_text: `检验标注 ${index + 1}`,
    item_type: "linear_dimension" as const,
    page_index: 0,
    active: true,
  }));
  const props = {
    items,
    balloons: [],
    filter: "all" as const,
    onSelectItem: vi.fn(),
  };
  const { container, rerender } = render(
    <InspectionItemTable {...props} selectedItemId="internal-0" />,
  );
  scrollIntoView.mockClear();

  rerender(<InspectionItemTable {...props} selectedItemId="internal-50" />);

  expect(screen.getByText("第 2 / 2 页")).not.toBeNull();
  const selectedRow = screen.getByRole("row", { name: /检验标注 51/ });
  expect(selectedRow.getAttribute("data-selected")).toBe("true");
  expect(container.querySelectorAll("[role='row'][data-item-id]").length)
    .toBeLessThanOrEqual(50);
  await waitFor(() => {
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "nearest",
      inline: "nearest",
    });
  });
});

test("未知后端枚举只显示安全中文占位，表头不使用 inline style", () => {
  render(
    <InspectionItemTable
      items={[
        {
          item_id: "unknown-item",
          raw_text: "未知标注",
          coarse_type: "future_backend_type",
          status: "future_backend_status",
          active: true,
        },
      ]}
      balloons={[
        {
          id: "unknown-balloon",
          itemId: "unknown-item",
          sourceId: "source",
          pageIndex: 0,
          center: [30, 30],
          number: 1,
          version: 1,
          status: "active",
          sortOrder: 0,
          placementStatus: "placed",
          collisionFlags: ["future_collision_flag"],
          leaderTarget: [20, 20],
        },
      ]}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  expect(document.body.textContent).not.toContain("future_backend_type");
  expect(document.body.textContent).not.toContain("future_backend_status");
  expect(document.body.textContent).not.toContain("future_collision_flag");
  expect(screen.getByRole("row", { name: /未知标注/ }).textContent).toContain("—");
  const header = document.querySelector(".inspection-table__head")!;
  expect(header.getAttribute("style")).toBeNull();
});

test("候选序号使用蓝色圆标，且有效正式气泡编号优先", () => {
  render(
    <InspectionItemTable
      items={[
        {
          item_id: "formal-item",
          raw_text: "正式编号项",
          active: true,
        },
        {
          item_id: "candidate-item",
          raw_text: "候选编号项",
          active: true,
        },
        {
          item_id: "empty-item",
          raw_text: "无编号项",
          active: false,
        },
      ]}
      balloons={[{
        id: "formal-balloon",
        itemId: "formal-item",
        center: [30, 30],
        number: 9,
        status: "active",
      }]}
      candidateNumbers={new Map([
        ["formal-item", 1],
        ["candidate-item", 2],
      ])}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  const formalNumber = screen.getByRole("row", { name: /正式编号项/ })
    .querySelector(".inspection-number");
  expect(formalNumber?.textContent).toBe("9");
  expect(formalNumber?.classList.contains("inspection-number--formal")).toBe(true);
  expect(screen.queryByLabelText("候选序号 1")).toBeNull();

  const candidateNumber = screen.getByLabelText("候选序号 2");
  expect(candidateNumber.textContent).toBe("2");
  expect(candidateNumber.classList.contains("inspection-number--candidate")).toBe(true);

  const emptyNumber = screen.getByRole("row", { name: /无编号项/ })
    .querySelector(".inspection-number");
  expect(emptyNumber?.textContent).toBe("—");
  expect(emptyNumber?.classList.contains("inspection-number--empty")).toBe(true);
});

test("缺少真实页码时列表保持空状态且不回填第 1 页", () => {
  render(
    <InspectionItemTable
      items={[{
        item_id: "page-unknown",
        raw_text: "页码未知标注",
        item_type: "thread",
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="page-unknown"
      onSelectItem={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  expect(screen.getByRole("row", { name: /页码未知标注/ }).textContent)
    .toContain("—");
});

test("检验项列表不再渲染 legacy SIP 字段组或确认操作", () => {
  const { container } = render(
    <InspectionItemTable
      items={[{
        item_id: "legacy-sip-item",
        raw_text: "M6",
        item_type: "thread",
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="legacy-sip-item"
      onSelectItem={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  const tableSection = container.querySelector(".inspection-table-section");
  expect(
    within(tableSection as HTMLElement)
      .queryByRole("group", { name: "SIP 确认字段" }),
  ).toBeNull();
  expect(
    within(tableSection as HTMLElement)
      .queryByRole("button", { name: "确认当前检验项 SIP" }),
  ).toBeNull();
  expect(tableSection?.textContent).not.toContain("确认当前检验项 SIP");
});

test("缺少 onCommand 时不渲染 SIP 字段组", () => {
  render(
    <InspectionItemTable
      items={[{
        item_id: "optional-command-item",
        raw_text: "M8",
        item_type: "thread",
        active: true,
      }]}
      balloons={[]}
      filter="all"
      selectedItemId="optional-command-item"
      onSelectItem={vi.fn()}
    />,
  );

  expect(
    screen.queryByRole("group", { name: "SIP 确认字段" }),
  ).toBeNull();
});

test("确认当前有效项一次性排除全部待确认来源", async () => {
  const onCommand = vi.fn().mockResolvedValue(true);
  render(
    <InspectionItemTable
      items={[
        { item_id: "i1", raw_text: "M6", active: true },
        { item_id: "i2", raw_text: "10", active: true },
      ]}
      balloons={[]}
      pendingSources={[
        {
          observationId: "observation-1",
          sourceId: "source-1",
          rawText: "设计",
          coordinates: [1, 2, 3, 4],
          pageIndex: 0,
        },
        {
          observationId: "observation-2",
          sourceId: "source-2",
          rawText: "日期",
          coordinates: [5, 6, 7, 8],
          pageIndex: 0,
        },
      ]}
      filter="review_required"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "确认当前有效项" }));
  expect(screen.getByText(
    "将保留当前 2 个有效检验项，并排除全部 2 条待确认来源。",
  )).not.toBeNull();
  expect(screen.getByText(
    "排除内容不会进入 SIP，也不会生成气泡。",
  )).not.toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "确认排除 2 条" }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
  expect(onCommand).toHaveBeenCalledWith({
    type: "ignore_sources",
    observation_ids: ["observation-1", "observation-2"],
  });
  expect(screen.queryByText(
    "将保留当前 2 个有效检验项，并排除全部 2 条待确认来源。",
  )).toBeNull();
});

test("批量确认取消不提交，失败时保留确认提示", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  render(
    <InspectionItemTable
      items={[{ item_id: "i1", raw_text: "M6", active: true }]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "设计",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="review_required"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "确认当前有效项" }));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(onCommand).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "确认排除 1 条" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "确认当前有效项" }));
  fireEvent.click(screen.getByRole("button", { name: "确认排除 1 条" }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: "确认排除 1 条" })).not.toBeNull();
});

test("存在未保存来源草稿时禁止批量确认", () => {
  render(
    <InspectionItemTable
      items={[{ item_id: "i1", raw_text: "M6", active: true }]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "设计",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="review_required"
      selectedSourceId="source-1"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
    target: { value: "设计说明" },
  });

  expect(screen.getByRole("button", { name: "确认当前有效项" })
    .hasAttribute("disabled")).toBe(true);
});

test("打开批量确认后修改来源草稿仍禁止最终提交", () => {
  const onCommand = vi.fn();
  render(
    <InspectionItemTable
      items={[{ item_id: "i1", raw_text: "M6", active: true }]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "设计",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="review_required"
      selectedSourceId="source-1"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "确认当前有效项" }));
  fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
    target: { value: "设计说明" },
  });

  const confirm = screen.getByRole("button", { name: "确认排除 1 条" });
  expect(confirm.hasAttribute("disabled")).toBe(true);
  fireEvent.click(confirm);
  expect(onCommand).not.toHaveBeenCalled();
});

test("待判定来源进入统一列表并产生显式 source review commands", () => {
  const onSelectSource = vi.fn();
  const onCommand = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "技术要求：去除毛刺",
        coordinates: [60, 70, 150, 84],
        pageIndex: 1,
      }]}
      filter="all"
      selectedSourceId="source-1"
      onSelectItem={vi.fn()}
      onSelectSource={onSelectSource}
      onCommand={onCommand}
    />,
  );

  const row = screen.getByRole("row", { name: /技术要求：去除毛刺/ });
  expect(row.textContent).toContain("原始来源");
  expect(row.textContent).toContain("第 2 页");
  expect(row.textContent).toContain("待判定来源");
  fireEvent.click(row);
  expect(onSelectSource).toHaveBeenCalledWith("source-1");

  expect(
    screen.getByRole("button", { name: "添加为检验项" })
      .hasAttribute("disabled"),
  ).toBe(true);
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "general_requirement" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));
  expect(onCommand).toHaveBeenLastCalledWith({
    type: "promote_source",
    observation_id: "observation-1",
    raw_text: "技术要求：去除毛刺",
    item_type: "general_requirement",
    scope: "local_feature",
    balloon_required: true,
    page_index: 1,
  });

  fireEvent.click(screen.getByRole("button", {
    name: "忽略，不作为检验项",
  }));
  expect(onCommand).toHaveBeenLastCalledWith({
    type: "ignore_source",
    observation_id: "observation-1",
  });
});

test("待判定来源编辑器使用分层决策布局并突出纳入动作", () => {
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-layout",
        sourceId: "source-layout",
        rawText: "A",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-layout"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={vi.fn()}
    />,
  );

  const editor = screen.getByRole("group", { name: "待判定来源处理" });
  expect(
    within(editor).getByRole("heading", {
      name: "待判定来源处理",
      level: 3,
    }),
  ).not.toBeNull();
  expect(editor.querySelector(".source-review-grid")).not.toBeNull();
  expect(editor.querySelector(".source-review-toggle")).not.toBeNull();

  const actions = editor.querySelector(".source-review-actions");
  expect(actions).not.toBeNull();
  expect(
    within(actions as HTMLElement)
      .getAllByRole("button")
      .map((button) => button.textContent),
  ).toEqual(["忽略，不作为检验项", "添加为检验项"]);
  expect(
    within(actions as HTMLElement)
      .getByRole("button", { name: "添加为检验项" })
      .classList.contains("source-review-actions__primary"),
  ).toBe(true);
});

test("待人工审核筛选包含待判定来源", () => {
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-1",
        sourceId: "source-1",
        rawText: "伟立机器人",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="review_required"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
    />,
  );
  expect(screen.getByRole("row", { name: /伟立机器人/ })).not.toBeNull();
});

test("待判定来源参与状态筛选和外部选择分页跳转", () => {
  const items = Array.from({ length: 50 }, (_, index) => ({
    item_id: `item-${index}`,
    raw_text: `检验项 ${index + 1}`,
    active: true,
  }));
  const props = {
    items,
    balloons: [],
    pendingSources: [{
      observationId: "observation-late",
      sourceId: "source-late",
      rawText: "第二页来源标注",
      coordinates: [1, 2, 3, 4] as [number, number, number, number],
      pageIndex: 0,
    }],
    filter: "all" as const,
    onSelectItem: vi.fn(),
    onSelectSource: vi.fn(),
  };
  const { rerender } = render(<InspectionItemTable {...props} />);

  rerender(
    <InspectionItemTable {...props} selectedSourceId="source-late" />,
  );
  expect(screen.getByText("第 2 / 2 页")).not.toBeNull();
  expect(screen.getByRole("row", { name: /第二页来源标注/ })
    .getAttribute("data-selected")).toBe("true");

  fireEvent.change(screen.getByRole("combobox", { name: "筛选状态" }), {
    target: { value: "source_pending" },
  });
  expect(screen.getByRole("row", { name: /第二页来源标注/ })).not.toBeNull();
  expect(screen.queryByRole("row", { name: /检验项 1/ })).toBeNull();
});

test("来源命令成功后保留草稿值并只清理未保存标记", async () => {
  const onDraftChange = vi.fn();
  const onCommand = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-draft",
        sourceId: "source-draft",
        rawText: "原始来源文字",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-draft"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
    target: { value: "修订后的来源文字" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "thread" },
  });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));

  await waitFor(() => {
    expect(onCommand).toHaveBeenCalledOnce();
    expect(onDraftChange).toHaveBeenLastCalledWith(false);
  });
  expect(
    (screen.getByRole("textbox", { name: "原始标注" }) as HTMLInputElement)
      .value,
  ).toBe("修订后的来源文字");
});

test("来源 promote 失败时保留编辑后的文字、类型和未保存状态", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  const onDraftChange = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-retry",
        sourceId: "source-retry",
        rawText: "原始来源文字",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-retry"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  const rawText = screen.getByRole(
    "textbox",
    { name: "原始标注" },
  ) as HTMLInputElement;
  const itemType = screen.getByRole(
    "combobox",
    { name: "检验类型" },
  ) as HTMLSelectElement;
  fireEvent.change(rawText, { target: { value: "修订后来源文字" } });
  fireEvent.change(itemType, { target: { value: "thread" } });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "promote_source",
    observation_id: "observation-retry",
    raw_text: "修订后来源文字",
    item_type: "thread",
    scope: "local_feature",
    balloon_required: true,
    page_index: 0,
  }));
  expect(rawText.value).toBe("修订后来源文字");
  expect(itemType.value).toBe("thread");
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
});

test("来源 ignore 失败时保留来源草稿和未保存状态", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  const onDraftChange = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-ignore-retry",
        sourceId: "source-ignore-retry",
        rawText: "待忽略来源",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-ignore-retry"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  const rawText = screen.getByRole(
    "textbox",
    { name: "原始标注" },
  ) as HTMLInputElement;
  fireEvent.change(rawText, { target: { value: "待忽略来源（已复核）" } });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  fireEvent.click(screen.getByRole("button", {
    name: "忽略，不作为检验项",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "ignore_source",
    observation_id: "observation-ignore-retry",
  }));
  expect(rawText.value).toBe("待忽略来源（已复核）");
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
});

test("空白来源只在列表显示占位符且补全真实文字后才允许 promote", () => {
  const onCommand = vi.fn();
  render(
    <InspectionItemTable
      items={[]}
      balloons={[]}
      pendingSources={[{
        observationId: "observation-empty",
        sourceId: "source-empty",
        rawText: "",
        coordinates: [1, 2, 3, 4],
        pageIndex: 0,
      }]}
      filter="all"
      selectedSourceId="source-empty"
      onSelectItem={vi.fn()}
      onSelectSource={vi.fn()}
      onCommand={onCommand}
    />,
  );

  const row = screen.getByRole("row", { name: /原始来源.*待判定来源/ });
  const sourceCopy = row.querySelector(".inspection-item-copy strong");
  expect(sourceCopy?.textContent).toBe("—");
  expect(sourceCopy?.getAttribute("title")).toBe("—");

  const rawText = screen.getByRole("textbox", { name: "原始标注" });
  const promote = screen.getByRole("button", { name: "添加为检验项" });
  expect((rawText as HTMLInputElement).value).toBe("");
  fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
    target: { value: "general_requirement" },
  });
  expect(promote.hasAttribute("disabled")).toBe(true);

  fireEvent.change(rawText, { target: { value: "人工补录的真实要求" } });
  expect(promote.hasAttribute("disabled")).toBe(false);
  fireEvent.click(promote);
  expect(onCommand).toHaveBeenCalledWith({
    type: "promote_source",
    observation_id: "observation-empty",
    raw_text: "人工补录的真实要求",
    item_type: "general_requirement",
    scope: "local_feature",
    balloon_required: true,
    page_index: 0,
  });
});

test("审核队列保留原列表信息密度，仅用状态区分待人工审核与自动通过", () => {
  const items = [
    {
      item_id: "auto-item",
      raw_text: "自动项",
      status: "auto_accepted",
      requires_confirmation: false,
      balloon_required: true,
      acceptance_source: "confidence_policy" as const,
      confidence_decision: {
        band: "high" as const,
        review_disposition: "auto_accepted" as const,
        policy_version: "candidate-confidence/1" as const,
        evidence_codes: ["typed_schema_complete"],
      },
      active: true,
    },
    {
      item_id: "medium-item",
      raw_text: "中置信项",
      status: "pending",
      confidence_decision: {
        band: "medium" as const,
        review_disposition: "review_required" as const,
        policy_version: "candidate-confidence/1" as const,
        evidence_codes: ["typed_schema_complete", "coverage_unchecked"],
      },
      active: true,
    },
    {
      item_id: "low-item",
      raw_text: "低置信项",
      status: "pending",
      confidence_decision: {
        band: "low" as const,
        review_disposition: "review_required" as const,
        policy_version: "candidate-confidence/1" as const,
        evidence_codes: ["source_signal_invalid"],
      },
      active: true,
    },
    {
      item_id: "unknown-item",
      raw_text: "未知项",
      status: "future_status",
      active: true,
    },
  ];
  const { rerender } = render(
    <InspectionItemTable
      items={items}
      balloons={[]}
      filter="review_required"
      onSelectItem={vi.fn()}
    />,
  );

  expect(screen.queryByRole("row", { name: /自动项/ })).toBeNull();
  expect(screen.getByRole("row", { name: /中置信项/ }).textContent)
    .not.toContain("中置信度");
  expect(screen.getByRole("row", { name: /中置信项/ }).textContent)
    .not.toContain("typed_schema_complete、coverage_unchecked");
  expect(screen.getByRole("row", { name: /低置信项/ }).textContent)
    .not.toContain("低置信度");
  expect(screen.getByRole("row", { name: /未知项/ }).textContent)
    .toContain("待人工审核");

  rerender(
    <InspectionItemTable
      items={items}
      balloons={[]}
      filter="auto_accepted"
      onSelectItem={vi.fn()}
    />,
  );
  expect(screen.getByRole("row", { name: /自动项/ }).textContent)
    .toContain("自动通过");
  expect(screen.getByRole("row", { name: /自动项/ }).textContent)
    .not.toContain("高置信度");
  expect(screen.getByRole("row", { name: /自动项/ }).textContent)
    .not.toContain("typed_schema_complete");
  expect(screen.queryByRole("row", { name: /中置信项/ })).toBeNull();
});

test("已保留但未选择气泡的项目仍留在待人工审核筛选", () => {
  render(
    <InspectionItemTable
      items={[{
        item_id: "balloon-pending",
        raw_text: "3.2",
        status: "kept",
        requires_confirmation: false,
        balloon_required: null,
        active: true,
      }]}
      balloons={[]}
      filter="review_required"
      onSelectItem={vi.fn()}
    />,
  );

  expect(screen.getByRole("row", { name: /3.2.*待选择气泡/ })).not.toBeNull();
  expect(screen.queryByText("没有符合条件的检验项。")).toBeNull();
});

test("全部筛选保留自动通过项的选择身份", () => {
  const onSelectItem = vi.fn();
  render(
    <InspectionItemTable
      items={[{
        item_id: "auto-editable",
        raw_text: "自动通过可编辑",
        status: "auto_accepted",
        requires_confirmation: false,
        acceptance_source: "confidence_policy",
        confidence_decision: {
          band: "high",
          review_disposition: "auto_accepted",
          policy_version: "candidate-confidence/1",
          evidence_codes: ["typed_schema_complete"],
        },
        active: true,
      }]}
      balloons={[]}
      candidateNumbers={new Map([["auto-editable", 7]])}
      filter="all"
      selectedItemId="auto-editable"
      onSelectItem={onSelectItem}
    />,
  );

  const row = screen.getByRole("row", { name: /自动通过可编辑/ });
  expect(row.getAttribute("data-selected")).toBe("true");
  expect(screen.getByLabelText("自动通过气泡 7，待统一编号"))
    .not.toBeNull();
  fireEvent.click(row);
  expect(onSelectItem).toHaveBeenCalledWith("auto-editable");
});
