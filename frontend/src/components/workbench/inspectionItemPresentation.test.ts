import { describe, expect, test } from "vitest";

import { zhCN } from "../../copy/zhCN";
import { inspectionItemPresentation } from "./inspectionItemPresentation";


describe("inspectionItemPresentation", () => {
  test("正式气泡编号优先于候选编号", () => {
    expect(inspectionItemPresentation(
      {
        item_id: "item-1",
        item_type: "linear_dimension",
        raw_text: "48",
        active: true,
      },
      {
        id: "balloon-1",
        itemId: "item-1",
        center: [20, 30],
        number: 9,
        status: "active",
      },
      2,
    )).toMatchObject({
      displayNumber: 9,
      numberKind: "formal",
      numberLabel: zhCN.inspection.formalNumber(9),
    });
  });

  test("page_index 1 显示为第 2 页", () => {
    expect(inspectionItemPresentation({
      item_id: "item-2",
      raw_text: "85",
      page_index: 1,
      active: true,
    })).toMatchObject({
      page: 2,
      pageLabel: zhCN.inspection.sourcePage(2),
    });
  });

  test("kept 状态显示为已确认", () => {
    expect(inspectionItemPresentation({
      item_id: "item-3",
      raw_text: "M8",
      status: "kept",
      active: true,
    })).toMatchObject({
      status: "confirmed",
      statusLabel: zhCN.inspection.statusConfirmed,
    });
  });

  test("没有正式气泡时使用候选编号，完全无编号时不按数组索引回填", () => {
    expect(inspectionItemPresentation(
      {
        item_id: "item-4",
        raw_text: "R4",
        active: true,
      },
      undefined,
      4,
    )).toMatchObject({
      displayNumber: 4,
      numberKind: "candidate",
      numberLabel: zhCN.inspection.candidateNumber(4),
    });

    expect(inspectionItemPresentation({
      item_id: "item-5",
      raw_text: "无编号",
      active: true,
    })).toMatchObject({
      displayNumber: undefined,
      numberKind: "empty",
      numberLabel: zhCN.inspection.noNumber,
    });
  });

  test("未知或缺失的检验项类型使用统一安全占位", () => {
    expect(inspectionItemPresentation({
      item_id: "item-6",
      raw_text: "未知类型",
      coarse_type: "future_type",
      active: true,
    }).typeLabel).toBe(zhCN.workbench.unknown);
    expect(inspectionItemPresentation({
      item_id: "item-7",
      raw_text: "缺失类型",
      active: true,
    }).typeLabel).toBe(zhCN.workbench.unknown);
  });

  test("保留现有类型与页码优先级语义", () => {
    expect(inspectionItemPresentation(
      {
        item_id: "item-8",
        item_type: "thread",
        coarse_type: "roughness",
        raw_text: "M10",
        source_page: 7,
        page_index: 3,
        active: true,
      },
      {
        id: "balloon-8",
        itemId: "item-8",
        pageIndex: 1,
        center: [10, 20],
        number: 8,
        status: "active",
      },
    )).toMatchObject({
      typeLabel: zhCN.inspection.types.thread,
      page: 7,
      pageLabel: zhCN.inspection.sourcePage(7),
    });

    expect(inspectionItemPresentation(
      {
        item_id: "item-9",
        coarse_type: "roughness",
        raw_text: "Ra 3.2",
        active: true,
      },
      {
        id: "balloon-9",
        itemId: "item-9",
        pageIndex: 2,
        center: [10, 20],
        number: 9,
        status: "active",
      },
    )).toMatchObject({
      typeLabel: zhCN.review.coarseTypes.roughness,
      page: 3,
      pageLabel: zhCN.inspection.sourcePage(3),
    });
  });

  test.each([
    {
      name: "inactive 优先映射为 excluded",
      item: { active: false },
      balloon: {
        placementStatus: "manual_required" as const,
        collisionFlags: ["circle_overlap"],
      },
      expected: "excluded",
    },
    {
      name: "manual_required 优先于 collision",
      item: { active: true },
      balloon: {
        placementStatus: "manual_required" as const,
        collisionFlags: ["circle_overlap"],
      },
      expected: "manual",
    },
    {
      name: "碰撞映射为 collision",
      item: { active: true },
      balloon: { collisionFlags: ["circle_overlap"] },
      expected: "collision",
    },
    {
      name: "待确认状态映射为 pending",
      item: { active: true, requires_confirmation: true, status: "kept" },
      balloon: {},
      expected: "pending",
    },
    {
      name: "已确认 SIP 字段映射为 confirmed",
      item: { active: true, sip_detail_fields_confirmed: true },
      balloon: {},
      expected: "confirmed",
    },
    {
      name: "需要气泡但尚无气泡映射为 candidate",
      item: { active: true, balloon_required: true },
      balloon: undefined,
      expected: "candidate",
    },
    {
      name: "其他有效项映射为 pending",
      item: { active: true },
      balloon: {},
      expected: "pending",
    },
  ])("$name", ({ item, balloon, expected }) => {
    expect(inspectionItemPresentation(
      {
        item_id: "status-item",
        raw_text: "状态项",
        ...item,
      },
      balloon === undefined
        ? undefined
        : {
            id: "status-balloon",
            itemId: "status-item",
            center: [10, 20],
            number: 1,
            status: "active",
            ...balloon,
          },
    ).status).toBe(expected);
  });
});
