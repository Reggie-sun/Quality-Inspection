import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import {
  InspectionItemTable,
  SelectedInspectionItemSummary,
} from "./InspectionItemTable";


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

test("搜索、状态筛选和紧凑分页可处理大量检验项", () => {
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
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索检验项" }), {
    target: { value: "标注 51" },
  });
  expect(screen.getByRole("row", { name: /检验标注 51/ })).not.toBeNull();
  expect(screen.queryByRole("row", { name: /检验标注 1$/ })).toBeNull();
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

test("外部选择第 51 项时自动跳到第二页并显示选中行", () => {
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

  rerender(<InspectionItemTable {...props} selectedItemId="internal-50" />);

  expect(screen.getByText("第 2 / 2 页")).not.toBeNull();
  const selectedRow = screen.getByRole("row", { name: /检验标注 51/ });
  expect(selectedRow.getAttribute("data-selected")).toBe("true");
  expect(container.querySelectorAll("[role='row'][data-item-id]").length)
    .toBeLessThanOrEqual(50);
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

test("所选检验项摘要明确区分候选、正式和无序号状态", () => {
  const item = {
    item_id: "selected-item",
    raw_text: "选中检验项",
    active: true,
  };
  const { rerender } = render(
    <SelectedInspectionItemSummary
      item={item}
      candidateNumber={2}
    />,
  );

  const summary = screen.getByRole("region", { name: "所选检验项" });
  const candidate = within(summary).getByLabelText("候选序号 2");
  expect(candidate.classList.contains("selected-inspection-number--candidate"))
    .toBe(true);

  rerender(
    <SelectedInspectionItemSummary
      item={item}
      balloon={{
        id: "formal-balloon",
        itemId: "selected-item",
        center: [30, 30],
        number: 9,
        status: "active",
      }}
      candidateNumber={2}
    />,
  );

  const formal = within(summary).getByLabelText("正式序号 9");
  expect(formal.classList.contains("selected-inspection-number--formal")).toBe(true);
  expect(within(summary).queryByLabelText("候选序号 2")).toBeNull();

  rerender(
    <SelectedInspectionItemSummary item={item} />,
  );

  const empty = within(summary).getByLabelText("暂无序号");
  expect(empty.textContent).toBe("—");
  expect(empty.classList.contains("selected-inspection-number--empty")).toBe(true);
});

test("缺少真实页码时列表和详情保持空状态且不回填第 1 页", () => {
  const onDraftChange = vi.fn();
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
      onDraftChange={onDraftChange}
    />,
  );

  expect(screen.getByRole("row", { name: /页码未知标注/ }).textContent)
    .toContain("—");
  expect(
    (screen.getByRole("spinbutton", {
      name: "页码：页码未知标注",
    }) as HTMLInputElement).value,
  ).toBe("");

  fireEvent.change(screen.getByRole("textbox", {
    name: "检验方法：页码未知标注",
  }), { target: { value: "卡尺" } });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "取消 SIP 字段修改" }));
  expect(onDraftChange).toHaveBeenLastCalledWith(false);
});

test("切换检验项时保留尚未确认的 SIP 草稿和未保存状态", () => {
  const onDraftChange = vi.fn();
  const props = {
    items: [
      {
        item_id: "draft-1",
        raw_text: "标注一",
        item_type: "thread" as const,
        inspection_item: "项目一",
        inspection_standard: "标准一",
        inspection_method: "方法一",
        key_dimension: "重点一",
        inspection_role: "角色一",
        source_page: 1,
        active: true,
      },
      {
        item_id: "draft-2",
        raw_text: "标注二",
        item_type: "thread" as const,
        inspection_item: "项目二",
        inspection_standard: "标准二",
        inspection_method: "方法二",
        key_dimension: "重点二",
        inspection_role: "角色二",
        source_page: 2,
        active: true,
      },
    ],
    balloons: [],
    filter: "all" as const,
    onSelectItem: vi.fn(),
    onCommand: vi.fn(),
    onDraftChange,
  };
  const { rerender } = render(
    <InspectionItemTable {...props} selectedItemId="draft-1" />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：标注一" }), {
    target: { value: "更新方法" },
  });
  rerender(<InspectionItemTable {...props} selectedItemId="draft-2" />);
  expect(onDraftChange).toHaveBeenLastCalledWith(true);

  rerender(<InspectionItemTable {...props} selectedItemId="draft-1" />);
  expect(
    (screen.getByRole("textbox", { name: "检验方法：标注一" }) as HTMLInputElement)
      .value,
  ).toBe("更新方法");
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
});
