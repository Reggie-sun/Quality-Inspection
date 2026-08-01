import { describe, expect, test } from "vitest";

import { zhCN } from "../../copy/zhCN";
import {
  inspectionItemPresentation,
  isReviewRequiredItem,
} from "./inspectionItemPresentation";


describe("inspectionItemPresentation", () => {
  test("空控制框保留原始标注并显示未确认几何公差", () => {
    expect(inspectionItemPresentation({
      item_id: "gdt-unknown",
      item_type: "geometric_tolerance",
      raw_text: "∥ ? A",
      tolerance_type: "parallelism",
      frames: [],
      active: true,
    })).toMatchObject({
      typeLabel: "未确认几何公差",
      valueLabel: "∥ ? A",
      datumLabels: [],
    });
  });

  test("typed GD&T renders subtype, value and ordered datum labels", () => {
    expect(inspectionItemPresentation({
      item_id: "gdt-parallelism",
      item_type: "geometric_tolerance",
      raw_text: "∥ 0.1 A",
      normalized_text: "∥ | 0.1 | A",
      tolerance_type: "parallelism",
      tolerance_symbol: "∥",
      tolerance_value: "0.1",
      diameter_modifier: false,
      modifiers: [],
      datum_references: [{ datum: "A", modifiers: [] }],
      frames: [{
        segments: [{
          tolerance_value: "0.1",
          diameter_modifier: false,
          modifiers: [],
          datum_references: [{ datum: "A", modifiers: [] }],
        }],
      }],
      schema_version: "geometric-tolerance-candidate/1",
      standard_context: "unspecified",
      coordinates: [1, 2, 3, 4],
      source_location_ids: ["gdt-source"],
      source_type: "automatic",
      status: "pending",
      requires_confirmation: true,
      evidence_ref: "asset://gdt",
      active: true,
    })).toMatchObject({
      typeLabel: "平行度",
      valueLabel: "0.1",
      datumLabels: ["基准 A"],
    });
  });

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
      balloon_required: true,
      active: true,
    })).toMatchObject({
      status: "confirmed",
      statusLabel: zhCN.inspection.statusConfirmed,
    });
  });

  test("kept 但未选择气泡时继续显示为待处理", () => {
    const item = {
      item_id: "balloon-pending-item",
      raw_text: "3.2",
      status: "kept",
      requires_confirmation: false,
      balloon_required: null,
      active: true,
    } as const;

    expect(inspectionItemPresentation(item)).toMatchObject({
      status: "pending",
      statusLabel: "待选择气泡",
    });
    expect(isReviewRequiredItem(item)).toBe(true);
  });

  test("精确 auto_accepted 显示自动通过气泡名称", () => {
    expect(inspectionItemPresentation(
      {
        item_id: "auto-item",
        raw_text: "10",
        status: "auto_accepted",
        requires_confirmation: false,
        balloon_required: true,
        acceptance_source: "confidence_policy",
        confidence_decision: {
          band: "high",
          review_disposition: "auto_accepted",
          policy_version: "candidate-confidence/1",
          evidence_codes: ["typed_schema_complete", "coverage_clear"],
        },
        active: true,
      },
      undefined,
      3,
    )).toMatchObject({
      status: "auto_accepted",
      statusLabel: "自动通过",
      numberKind: "candidate",
      numberLabel: "自动通过气泡 3",
    });
  });

  test.each([
    {
      name: "requires_confirmation 为 true",
      requires_confirmation: true,
      acceptance_source: "confidence_policy",
    },
    {
      name: "requires_confirmation 缺失",
      requires_confirmation: undefined,
      acceptance_source: "confidence_policy",
    },
    {
      name: "acceptance_source 缺失",
      requires_confirmation: false,
      acceptance_source: undefined,
    },
    {
      name: "acceptance_source 与自动策略矛盾",
      requires_confirmation: false,
      acceptance_source: "manual",
    },
  ])("$name 时不得自动通过或退出人工队列", ({
    requires_confirmation,
    acceptance_source,
  }) => {
    const item = {
      item_id: "contradictory-auto-item",
      raw_text: "10",
      status: "auto_accepted",
      requires_confirmation,
      acceptance_source,
      confidence_decision: {
        band: "high",
        review_disposition: "auto_accepted",
        policy_version: "candidate-confidence/1",
        evidence_codes: ["typed_schema_complete"],
      },
      active: true,
    } as const;

    expect(inspectionItemPresentation(item as never)).toMatchObject({
      status: "pending",
      statusLabel: "待人工审核",
    });
    expect(isReviewRequiredItem(item as never)).toBe(true);
  });

  test.each([
    {
      name: "active kept 仍待确认",
      item: {
        active: true,
        status: "kept",
        requires_confirmation: true,
      },
      expected: true,
    },
    {
      name: "完整自动通过项",
      item: {
        active: true,
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
      },
      expected: false,
    },
    {
      name: "inactive kept 仍待确认",
      item: {
        active: false,
        status: "kept",
        requires_confirmation: true,
      },
      expected: false,
    },
  ])("$name 的默认人工队列归属为 $expected", ({ item, expected }) => {
    expect(isReviewRequiredItem({
      item_id: "queue-item",
      raw_text: "10",
      ...item,
    } as never)).toBe(expected);
  });

  test("未知 confidence/status fail closed 为待人工审核", () => {
    expect(inspectionItemPresentation({
      item_id: "unknown-confidence",
      raw_text: "未知投影",
      status: "future_status",
      confidence_decision: {
        band: "future_band",
        review_disposition: "future_disposition",
        policy_version: "future-policy",
        evidence_codes: [],
      } as never,
      active: true,
    })).toMatchObject({
      status: "pending",
      statusLabel: "待人工审核",
    });
  });

  test.each([
    {
      name: "缺少 status 与 decision",
      item: {},
    },
    {
      name: "未知 status",
      item: {
        status: "future_status",
        confidence_decision: {
          band: "high",
          review_disposition: "auto_accepted",
          policy_version: "candidate-confidence/1",
          evidence_codes: ["typed_schema_complete"],
        },
      },
    },
    {
      name: "未知 band",
      item: {
        status: "auto_accepted",
        confidence_decision: {
          band: "future_band",
          review_disposition: "auto_accepted",
          policy_version: "candidate-confidence/1",
          evidence_codes: ["typed_schema_complete"],
        },
      },
    },
    {
      name: "未知 disposition",
      item: {
        status: "auto_accepted",
        confidence_decision: {
          band: "high",
          review_disposition: "future_disposition",
          policy_version: "candidate-confidence/1",
          evidence_codes: ["typed_schema_complete"],
        },
      },
    },
  ])("$name 且需要气泡时仍显示待人工审核", ({ item }) => {
    expect(inspectionItemPresentation(
      {
        item_id: "fail-closed-item",
        raw_text: "10",
        balloon_required: true,
        active: true,
        ...item,
      } as never,
      undefined,
      8,
    )).toMatchObject({
      displayNumber: 8,
      numberKind: "candidate",
      status: "pending",
      statusLabel: "待人工审核",
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
      item: {
        active: true,
        sip_detail_fields_confirmed: true,
        balloon_required: false,
      },
      balloon: {},
      expected: "confirmed",
    },
    {
      name: "需要气泡但没有明确后端状态仍 fail closed",
      item: { active: true, balloon_required: true },
      balloon: undefined,
      expected: "pending",
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
