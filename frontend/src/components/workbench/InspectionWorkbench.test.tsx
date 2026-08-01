import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type {
  ExportArtifactKind,
  ExportJob,
  PostJson,
  ProjectWorkbenchSipMetadataSuggestion,
  ReviewWorkingCopyView,
} from "../../api/types";
import { InspectionWorkbench } from "./InspectionWorkbench";


afterEach(cleanup);

function openAuxiliaryPanel(): void {
  fireEvent.click(screen.getByRole("button", {
    name: "展开检验、导出与处理信息",
  }));
}

function getSipRegion(): HTMLElement {
  const visibleRegion = screen.queryByRole("region", { name: "SIP 信息" });
  if (visibleRegion !== null) return visibleRegion;
  openAuxiliaryPanel();
  return screen.getByRole("region", { name: "SIP 信息" });
}

function successfulExport(): ExportJob {
  const artifact = (kind: ExportArtifactKind) => ({
    kind,
    sha256: `${kind}-sha256`,
    size_bytes: 1,
    reviewed_result_id: "reviewed-1",
    downloadable: true,
  });
  return {
    id: "export-success",
    project_id: "project-1",
    reviewed_result_id: "reviewed-1",
    status: "success",
    error_id: null,
    template_version: "template/1",
    mapping_version: "mapping/1",
    renderer_version: "renderer/1",
    artifacts: [
      artifact("ballooned_pdf"),
      artifact("sip_excel"),
      artifact("manifest"),
    ],
  };
}

function metadataSuggestion(
  field: ProjectWorkbenchSipMetadataSuggestion["field"],
  value: string,
): ProjectWorkbenchSipMetadataSuggestion {
  return {
    field,
    value,
    observation_id: `${field}-value`,
    label_observation_id: `${field}-label`,
    page_index: 0,
    bbox_pdf: [1, 2, 3, 4],
    rule_version: "welli-title-metadata/1",
    evidence_codes: ["native_line"],
  };
}

const duplicateExampleItems = [
  {
    item_id: "item-1",
    item_type: "linear_dimension" as const,
    raw_text: "⌀10",
    active: true,
  },
  {
    item_id: "item-2",
    item_type: "general_requirement" as const,
    raw_text: "±0.1",
    active: true,
  },
];

describe("InspectionWorkbench", () => {
  test("刷新后默认选中全部并展示自动通过与待人工审核项", () => {
    const items = [
      {
        item_id: "auto-item",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        status: "auto_accepted",
        requires_confirmation: false,
        acceptance_source: "confidence_policy" as const,
        confidence_decision: {
          band: "high" as const,
          review_disposition: "auto_accepted" as const,
          policy_version: "candidate-confidence/1" as const,
          evidence_codes: ["typed_schema_complete"],
        },
        balloon_required: true,
        active: true,
      },
      {
        item_id: "review-item",
        item_type: "linear_dimension" as const,
        raw_text: "20",
        status: "pending",
        requires_confirmation: true,
        active: true,
      },
    ];

    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "refresh-default-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 1 },
          manual_review_count: 1,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("button", { name: "筛选全部" })
      .getAttribute("data-active")).toBe("true");
    expect(screen.getByRole("row", { name: /10/ })).not.toBeNull();
    expect(screen.getByRole("row", { name: /20/ })).not.toBeNull();
  });

  test("顶部只保留项目摘要与返回列表且无草稿时直接返回", () => {
    const onReset = vi.fn();
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "working-1",
          project_id: "project-1",
          raw_result_id: "raw-1",
          version: 1,
          created_at: "2026-07-30T00:00:00Z",
          updated_at: "2026-07-30T00:00:00Z",
          manual_review_count: 0,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onReset={onReset}
      />,
    );

    const compactHeader = screen.getByRole("group", {
      name: "项目与审核操作",
    });
    expect(compactHeader.children).toHaveLength(1);
    expect(within(compactHeader).getByRole("region", {
      name: "项目摘要",
    })).not.toBeNull();
    expect(screen.queryByRole("button", { name: "冻结检验项" })).toBeNull();
    expect(screen.queryByRole("button", { name: "生成气泡" })).toBeNull();
    expect(screen.queryByRole("button", { name: "确认审核结果" })).toBeNull();

    fireEvent.click(within(compactHeader).getByRole("button", {
      name: "回到图纸列表",
    }));
    expect(onReset).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("审核界面不向用户暴露重复项合并工具", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={duplicateExampleItems}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.queryByRole("button", { name: "合并重复项" })).toBeNull();
    expect(screen.queryByText(
      "仅用于同一检验要求被重复识别，或一条标注被拆成多项的情况。",
    )).toBeNull();
    expect(screen.queryAllByRole("checkbox", {
      name: /选择检验项/,
    })).toHaveLength(0);
  });

  test("本地草稿立即显示未保存且只在保存修改时提交", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[{
          item_id: "i1",
          item_type: "thread",
          raw_text: "M6",
          active: true,
        }]}
        onSave={onSave}
      />,
    );

    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    expect(saveStatus.textContent).toBe("已保存");

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：M6",
    }));
    fireEvent.change(screen.getByRole("textbox", { name: "螺纹规格：M6" }), {
      target: { value: "M8" },
    });

    expect(saveStatus.textContent).toBe("有未保存修改");
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", {
      name: "保存修改检验项：M6",
    }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "edit",
      item_id: "i1",
      fields: {
        raw_text: "M6",
        thread_spec: "M8",
      },
    }));
  });

  test("未保存的 ReviewPanel 编辑阻止从列表切换检验项", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[
          {
            item_id: "item-10",
            item_type: "linear_dimension",
            raw_text: "10",
            active: true,
          },
          {
            item_id: "item-20",
            item_type: "linear_dimension",
            raw_text: "20",
            active: true,
          },
        ]}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const nominal = screen.getByRole("textbox", {
      name: "基本尺寸：10",
    }) as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(nominal, { target: { value: "10.0" } });

    fireEvent.click(screen.getByRole("row", { name: /20/ }));

    expect(screen.queryByRole("region", { name: "所选检验项" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "基本尺寸：20" })).toBeNull();
    expect(nominal.value).toBe("10.0");
    expect(within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status").textContent).toBe("请先保存或取消当前检验项修改");
  });

   test("被阻止切换后保存失败优先显示失败并保留编辑草稿", async () => {
    let rejectSave!: (reason?: unknown) => void;
    const onSave = vi.fn(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectSave = reject;
        }),
    );
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[
          {
            item_id: "item-10",
            item_type: "linear_dimension",
            raw_text: "10",
            active: true,
          },
          {
            item_id: "item-20",
            item_type: "linear_dimension",
            raw_text: "20",
            active: true,
          },
        ]}
        onSave={onSave}
      />,
    );

    const nominal = screen.getByRole("textbox", {
      name: "基本尺寸：10",
    }) as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(nominal, { target: { value: "10.0" } });
    fireEvent.click(screen.getByRole("row", { name: /20/ }));
    fireEvent.click(screen.getByRole("button", {
      name: "保存修改检验项：10",
    }));

    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    fireEvent.click(screen.getByRole("row", { name: /20/ }));
    rejectSave(new Error("save failed"));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "edit",
        item_id: "item-10",
        fields: {
          raw_text: "10",
          nominal: "10.0",
        },
      });
      expect(saveStatus.textContent).toBe("保存失败");
    });
    expect(nominal.value).toBe("10.0");
    expect(nominal.hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", {
      name: "保存修改检验项：10",
    }).hasAttribute("disabled")).toBe(false);
  });

  test("被拒绝的 PDF 候选项不会在后续选择来源时恢复选中", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const items = [
      {
        item_id: "item-10",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        active: true,
      },
      {
        item_id: "item-20",
        item_type: "linear_dimension" as const,
        raw_text: "20",
        active: true,
      },
    ];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[{
          id: "candidate-20",
          itemId: "item-20",
          candidateNumber: 2,
          pageIndex: 0,
          bbox: [30, 40, 50, 60],
          rawText: "20",
        }]}
        sources={[{
          id: "pending-source",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "来源待判定 12",
        }]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw-result",
          version: 1,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: 1,
            entries: [{
              observation_id: "pending-observation",
              source_location_id: "pending-source",
              candidate_id: null,
              disposition: "ambiguous",
              coordinates: [60, 70, 150, 84],
              requires_confirmation: true,
            }],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(screen.getByRole("textbox", {
      name: "基本尺寸：10",
    }), { target: { value: "10.0" } });

    const candidate = screen.getByTestId("candidate-number-candidate-20");
    fireEvent.click(candidate);
    expect(screen.getByRole("article", {
      name: "检验项 — · 线性尺寸",
    })).not.toBeNull();
    expect(candidate.getAttribute("data-selected")).toBe("false");

    fireEvent.click(screen.getByRole("button", {
      name: "保存修改检验项：10",
    }));
    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "edit",
        item_id: "item-10",
        fields: {
          raw_text: "10",
          nominal: "10.0",
        },
      });
      expect(saveStatus.textContent).toBe("已保存");
    });

    fireEvent.click(screen.getByRole("row", { name: /来源待判定/ }));
    expect(screen.getByTestId("source-pending-source").getAttribute("data-selected"))
      .toBe("true");
    expect(candidate.getAttribute("data-selected")).toBe("false");
  });

  test("未保存编辑阻止来源和 PDF 气泡选择，保存后清除提示并恢复切换", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const items = [
      {
        item_id: "item-10",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        active: true,
      },
      {
        item_id: "item-20",
        item_type: "linear_dimension" as const,
        raw_text: "20",
        active: true,
      },
    ];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "pending-source",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "来源待判定 12",
        }]}
        balloons={[{
          id: "balloon-20",
          itemId: "item-20",
          pageIndex: 0,
          center: [80, 90],
          number: 2,
          status: "active",
        }]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw-result",
          version: 1,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: 1,
            entries: [{
              observation_id: "pending-observation",
              source_location_id: "pending-source",
              candidate_id: null,
              disposition: "ambiguous",
              coordinates: [60, 70, 150, 84],
              requires_confirmation: true,
            }],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(screen.getByRole("textbox", {
      name: "基本尺寸：10",
    }), { target: { value: "10.0" } });

    const source = screen.getByRole("row", { name: /来源待判定/ });
    const balloon = screen.getByTestId("balloon-balloon-20");
    fireEvent.click(source);
    fireEvent.click(balloon);

    expect(screen.getByRole("article", {
      name: "检验项 — · 线性尺寸",
    })).not.toBeNull();
    expect(screen.getByTestId("source-pending-source").getAttribute("data-selected"))
      .toBe("false");
    expect(balloon.getAttribute("data-selected")).toBe("false");
    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    expect(saveStatus.textContent).toBe("请先保存或取消当前检验项修改");

    fireEvent.click(screen.getByRole("button", {
      name: "保存修改检验项：10",
    }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "edit",
        item_id: "item-10",
        fields: {
          raw_text: "10",
          nominal: "10.0",
        },
      });
      expect(saveStatus.textContent).toBe("已保存");
    });

    fireEvent.click(source);
    expect(screen.getByTestId("source-pending-source").getAttribute("data-selected"))
      .toBe("true");
    expect(screen.queryByRole("article", {
      name: "检验项 — · 线性尺寸",
    })).toBeNull();

    fireEvent.click(balloon);
    expect(screen.getByRole("article", {
      name: "检验项 2 · 线性尺寸",
    })).not.toBeNull();
    expect(balloon.getAttribute("data-selected")).toBe("true");
  });

  test("外部操作反馈仅显示在项目摘要的保存状态中", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        actionState="审核修改已提交"
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const summary = screen.getByRole("region", { name: "项目摘要" });
    expect(within(summary).getByRole("status").textContent).toBe("审核修改已提交");
    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    fireEvent.change(within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }), { target: { value: "未保存名称" } });
    expect(within(summary).getByRole("status").textContent)
      .toBe("有未保存修改");
    expect(screen.queryByRole("region", { name: "审核流程操作" })).toBeNull();
  });

  test("无最终审核 handlers 时不渲染空操作区且不重复全局头部", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const shell = screen.getByRole("main");
    const compactHeader = screen.getByRole("group", {
      name: "项目与审核操作",
    });
    const projectSummary = screen.getByRole("region", { name: "项目摘要" });
    const children = Array.from(shell.children);

    expect(children.indexOf(compactHeader)).toBe(0);
    expect(within(compactHeader).getByRole("region", {
      name: "项目摘要",
    })).toBe(projectSummary);
    expect(compactHeader.children).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "审核流程操作" })).toBeNull();
    expect(screen.queryByText("工程图纸检验工作台")).toBeNull();
    expect(screen.queryByRole("heading", { name: "检验项目审核" })).toBeNull();
    expect(screen.queryByRole("button", { name: "保存审核修改" })).toBeNull();
  });

  test("明确审核动作直接提交且不渲染额外保存按钮", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[
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
        ]}
        onSave={onSave}
      />,
    );

    expect(screen.queryByRole("button", { name: "保存审核修改" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "keep",
      item_id: "i1",
    }));
    expect(within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status").textContent).toBe("已保存");
  });

  test("审核命令请求期间阻止第二个明确动作", async () => {
    let resolveSave!: () => void;
    const onSave = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSave = resolve;
        }),
    );
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[
          {
            item_id: "i1",
            item_type: "thread",
            raw_text: "M6",
            active: true,
          },
        ]}
        onSave={onSave}
      />,
    );
    const keep = screen.getByRole("button", { name: "保留检验项：M6" });
    const exclude = screen.getByRole("button", { name: "排除检验项：M6" });
    fireEvent.click(keep);
    fireEvent.click(exclude);

    expect(onSave).toHaveBeenCalledOnce();
    expect(exclude.hasAttribute("disabled")).toBe(true);

    resolveSave();
    await waitFor(() => expect(exclude.hasAttribute("disabled")).toBe(false));
  });

  test("展示真实项目摘要、两栏区域和默认收起的工作区", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[{
          item_id: "hidden-item-uuid",
          item_type: "thread",
          raw_text: "M6",
          page_index: 0,
          status: "kept",
          balloon_required: true,
          active: true,
        }]}
        workingCopy={{
          id: "hidden-working-uuid",
          project_id: "hidden-project-uuid",
          raw_result_id: "hidden-raw-uuid",
          version: 3,
          items: [{
            item_id: "hidden-item-uuid",
            item_type: "thread",
            raw_text: "M6",
            page_index: 0,
            status: "kept",
            active: true,
          }],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        projectState="editing"
        projectId="hidden-project-uuid"
        reviewedResultId={undefined}
        exportPost={vi.fn()}
        operatorId="hidden-operator-uuid"
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const projectSummary = screen.getByRole("region", { name: "项目摘要" });
    for (const value of ["上座", "JS26032501", "A1"]) {
      expect(projectSummary.textContent).toContain(value);
    }
    expect(screen.getByRole("region", { name: "工程图纸" })).not.toBeNull();
    expect(screen.getByRole("region", { name: "检验项审核" })).not.toBeNull();
    expect(screen.queryByRole("complementary", { name: "检验、导出与处理信息" }))
      .toBeNull();
    const workspaceButton = screen.getByRole("button", {
      name: "展开检验、导出与处理信息",
    });
    expect(workspaceButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(workspaceButton);

    expect(workspaceButton.getAttribute("aria-expanded")).toBe("true");
    const aside = screen.getByRole("complementary", {
      name: "检验、导出与处理信息",
    });
    expect(within(aside).queryByRole("region", { name: "SIP基本信息" }))
      .toBeNull();
    expect(within(aside).getByRole("region", {
      name: "正式文件导出",
    })).not.toBeNull();
    expect(within(aside).getByRole("region", {
      name: "公司处理记录",
    })).not.toBeNull();
    expect(within(aside).getByText("暂无处理记录")).not.toBeNull();
    expect(document.body.textContent).not.toContain("hidden-project-uuid");
    expect(document.body.textContent).not.toContain("hidden-operator-uuid");
    expect(document.body.textContent).not.toContain("hidden-item-uuid");
    expect(document.body.textContent).not.toContain("自动保存");
    const actionLabels = screen.getAllByRole("button")
      .map((button) => button.textContent?.trim())
      .filter((label) => [
        "冻结检验项",
        "生成气泡",
        "确认审核结果",
        "生成正式文件",
      ].includes(label ?? ""));
    expect(actionLabels).toEqual(["生成正式文件"]);
  });

  test("检验项列表与编辑合并为同一紧凑工作区并保持操作顺序", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[{
          id: "balloon-1",
          itemId: "item-1",
          pageIndex: 0,
          center: [20, 30],
          number: 1,
          version: 1,
          status: "active",
          sortOrder: 0,
        }]}
        items={[{
          item_id: "item-1",
          item_type: "thread",
          raw_text: "M6",
          page_index: 0,
          status: "kept",
          balloon_required: true,
          active: true,
        }]}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onDeleteBalloon={vi.fn()}
        onRebuildBalloon={vi.fn()}
        onReorderBalloon={vi.fn()}
        onRenumberBalloons={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "筛选全部" }));
    fireEvent.click(screen.getByRole("row", { name: /M6/ }));

    const reviewRegion = screen.getByRole("region", { name: "检验项审核" });
    expect(reviewRegion.classList.contains(
      "inspection-pane--with-technical-requirements",
    )).toBe(false);
    const recognitionSummary = screen.getByRole("region", { name: "识别汇总" });
    const workspace = screen.getByRole("group", {
      name: "检验项列表与编辑",
    });
    const toolbar = screen.getByRole("region", { name: "气泡操作" });
    const table = within(workspace).getByRole("table", {
      name: "检验项列表",
    });

    expect(workspace.querySelector(".inspection-review-workspace__list"))
      .not.toBeNull();
    expect(workspace.querySelector(".inspection-review-workspace__detail"))
      .not.toBeNull();
    expect(table.closest(".inspection-table-section")?.classList.contains(
      "inspection-table-section--compact",
    )).toBe(true);
    const detail = within(workspace).getByRole("article", {
      name: "检验项 1 · 螺纹",
    });
    expect(within(detail).getByRole("heading", {
      name: "检验项 1 · 螺纹",
    })).not.toBeNull();
    expect(within(detail).getByText("已确认")).not.toBeNull();
    expect(within(detail).getByText("气泡 1")).not.toBeNull();
    expect(within(detail).getByText("第 1 页")).not.toBeNull();
    expect(within(workspace).queryByRole("region", {
      name: "所选检验项",
    })).toBeNull();
    expect(document.querySelector(".candidate-editor")).toBeNull();

    const children = Array.from(reviewRegion.children);
    expect(children.indexOf(recognitionSummary))
      .toBeLessThan(children.indexOf(workspace));
    expect(children.indexOf(workspace)).toBeLessThan(children.indexOf(toolbar));
  });

  test("编辑所选检验项时持续显示语义身份、真实编号、页码和状态", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[
          {
            id: "balloon-17",
            itemId: "selected-hidden-uuid",
            pageIndex: 1,
            center: [20, 30],
            number: 17,
            status: "active",
            placementStatus: "placed",
            collisionFlags: [],
          },
        ]}
        items={[
          {
            item_id: "first-item",
            item_type: "linear_dimension",
            raw_text: "10",
            page_index: 0,
            status: "kept",
            active: true,
          },
          {
            item_id: "selected-hidden-uuid",
            item_type: "thread",
            raw_text: "M8",
            page_index: 1,
            status: "kept",
            balloon_required: true,
            active: true,
          },
        ]}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "筛选全部" }));
    fireEvent.click(screen.getByRole("row", { name: /M8/ }));

    const workspace = screen.getByRole("group", {
      name: "检验项列表与编辑",
    });
    const detail = within(workspace).getByRole("article", {
      name: "检验项 17 · 螺纹",
    });
    expect(within(detail).getByRole("heading", {
      name: "检验项 17 · 螺纹",
    })).not.toBeNull();
    for (const value of ["气泡 17", "第 2 页", "已确认"]) {
      expect(detail.textContent).toContain(value);
    }
    expect(detail.textContent).not.toContain("selected-hidden-uuid");
    expect(within(workspace).queryByRole("region", {
      name: "所选检验项",
    })).toBeNull();
    expect(screen.queryByText("识别原文")).toBeNull();
    expect(screen.queryByLabelText("识别原文：M8")).toBeNull();
  });

  test("检验、导出与处理信息展开后将 SIP 与当前检验项显示为独立区块", () => {
    const items = [{
      item_id: "reviewed-item",
      item_type: "thread" as const,
      raw_text: "M6",
      status: "kept",
      inspection_standard: "GB/T 197",
      inspection_role: "尺寸检验员",
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project-1",
          raw_result_id: "raw",
          version: 3,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        projectState="reviewed"
        projectId="project-1"
        reviewedResultId="reviewed-1"
        initialExport={successfulExport()}
        exportPost={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.queryByRole("region", { name: "SIP 信息" })).toBeNull();
    expect(screen.queryByRole("region", { name: "当前检验项" })).toBeNull();

    openAuxiliaryPanel();

    const aside = screen.getByRole("complementary", {
      name: "检验、导出与处理信息",
    });
    const exportRegion = screen.getByRole("region", {
      name: "正式文件导出",
    });
    const sipRegion = within(aside).getByRole("region", {
      name: "SIP 信息",
    });
    const selectedItemRegion = within(aside).getByRole("region", {
      name: "当前检验项",
    });
    expect(Array.from(aside.children).map((child) => (
      child.getAttribute("aria-label")
    ))).toEqual([
      "正式文件导出",
      "SIP 信息",
      "当前检验项",
      "公司处理记录",
    ]);
    expect(aside.firstElementChild).toBe(exportRegion);
    expect(sipRegion.parentElement).toBe(aside);
    expect(selectedItemRegion.parentElement).toBe(aside);
    expect(sipRegion.contains(selectedItemRegion)).toBe(false);
    expect(
      within(exportRegion).getAllByRole("link").map((link) => link.textContent),
    ).toEqual([
      "下载带气泡 PDF",
      "下载 SIP Excel",
      "下载校验清单",
    ]);
  });

  test("生成正式文件后收起再展开仍保留三份下载", async () => {
    const exportPost = vi.fn().mockResolvedValue(successfulExport());
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        projectId="project-1"
        reviewedResultId="reviewed-1"
        exportPost={exportPost as unknown as PostJson}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    openAuxiliaryPanel();
    fireEvent.click(screen.getByRole("button", { name: "生成正式文件" }));
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(3));

    fireEvent.click(screen.getByRole("button", {
      name: "收起检验、导出与处理信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开检验、导出与处理信息",
    }));

    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(exportPost).toHaveBeenCalledOnce();
  });

  test("正式文件生成中收起再展开仍保持禁用且不会重复提交", async () => {
    let resolveExport!: (value: unknown) => void;
    const exportPost = vi.fn(() => new Promise((resolve) => {
      resolveExport = resolve;
    }));
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        projectId="project-1"
        reviewedResultId="reviewed-1"
        exportPost={exportPost as unknown as PostJson}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    openAuxiliaryPanel();
    fireEvent.click(screen.getByRole("button", { name: "生成正式文件" }));
    await waitFor(() => expect(exportPost).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", {
      name: "收起检验、导出与处理信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开检验、导出与处理信息",
    }));

    const exportButton = screen.getByRole("button", { name: "生成正式文件" });
    expect(exportButton.hasAttribute("disabled")).toBe(true);
    fireEvent.click(exportButton);
    expect(exportPost).toHaveBeenCalledOnce();

    resolveExport(successfulExport());
    await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(3));
  });

  test("摘要分离已审核与已确认，并以真实 SIP 字段提交既有 metadata command", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const items = [
      {
        item_id: "reviewed-item",
        item_type: "thread" as const,
        raw_text: "M6",
        status: "kept",
        sip_detail_fields_confirmed: false,
        sip_mapping_exceptions: ["unsupported_item_type"],
        inspection_item: "螺纹检验",
        inspection_standard: "GB/T 197",
        inspection_method: "螺纹规",
        key_dimension: "是",
        inspection_role: "尺寸检验员",
        source_page: 1,
        remarks: "首件复核",
        active: true,
      },
      {
        item_id: "confirmed-item",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        status: "pending",
        sip_detail_fields_confirmed: true,
        active: true,
      },
      {
        item_id: "inactive-item",
        item_type: "radius" as const,
        raw_text: "R3",
        status: "kept",
        sip_detail_fields_confirmed: true,
        active: false,
      },
    ];
    const { container } = render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 3,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        projectState="editing"
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "筛选全部" }));
    fireEvent.click(screen.getByRole("row", { name: /M6/ }));
    const summary = within(
      screen.getByRole("region", { name: "项目摘要" }),
    );
    expect(summary.getByText("已审核").nextElementSibling?.textContent).toBe("1");
    expect(summary.getByText("SIP 表格").nextElementSibling?.textContent)
      .toBe("已生成 1 / 异常 1");
    expect(summary.getByText("保存状态").nextElementSibling?.textContent)
      .toBe("已保存");

    const sipRegion = getSipRegion();
    const aside = screen.getByRole("complementary", {
      name: "检验、导出与处理信息",
    });
    expect(screen.getAllByRole("region", { name: "SIP 信息" })).toHaveLength(1);
    expect(sipRegion.parentElement).toBe(aside);
    const projectRegion = within(sipRegion).getByRole("region", {
      name: "项目基本信息",
    });
    const currentRegion = within(aside).getByRole("region", {
      name: "当前检验项",
    });
    expect(currentRegion.parentElement).toBe(aside);
    expect(sipRegion.contains(currentRegion)).toBe(false);
    const sipSummary = projectRegion.querySelector("dl");
    expect(sipSummary).not.toBeNull();
    const sipCard = within(projectRegion);
    for (const label of [
      "物料编码",
      "产品名称",
      "图号",
      "版本号",
      "材质",
    ]) {
      expect(sipSummary?.textContent).toContain(label);
    }
    for (const duplicate of [
      "单位",
      "检验标准",
      "检验人员角色",
      "审核人员角色",
    ]) {
      expect(sipSummary?.textContent).not.toContain(duplicate);
    }
    expect(sipSummary?.textContent).toContain("产品名称上座");
    expect(sipSummary?.textContent).toContain("图号JS26032501");
    expect(sipSummary?.textContent).toContain("版本号A1");
    expect(sipSummary?.textContent).toContain("材质SUS304");
    expect(sipSummary?.querySelectorAll("dd")).toHaveLength(5);
    const selectedFields = within(currentRegion).getByRole("group", {
      name: "SIP 字段",
    });
    for (const [label, value] of [
      ["检验项目：M6", "螺纹检验"],
      ["检验标准：M6", "GB/T 197"],
      ["检验方法：M6", "螺纹规"],
      ["关键尺寸：M6", "是"],
      ["检验角色：M6", "尺寸检验员"],
      ["备注（可选）：M6", "首件复核"],
    ]) {
      expect((
        within(selectedFields).getByRole("textbox", {
          name: label,
        }) as HTMLInputElement
      ).value).toBe(value);
    }
    expect((
      within(selectedFields).getByRole("spinbutton", {
        name: "页码：M6",
      }) as HTMLInputElement
    ).value).toBe("1");

    const editorSummary = sipRegion.querySelector("summary");
    expect(editorSummary?.textContent).toBe("编辑项目 SIP 信息");
    fireEvent.click(editorSummary as HTMLElement);
    const confirmMetadata = sipCard.getByRole("button", {
      name: "保存补充信息",
    });
    expect(confirmMetadata.hasAttribute("disabled")).toBe(true);
    fireEvent.change(sipCard.getByRole("textbox", { name: "物料编码" }), {
      target: { value: "MAT-001" },
    });
    expect(summary.getByText("保存状态").nextElementSibling?.textContent)
      .toBe("有未保存修改");
    expect(confirmMetadata.hasAttribute("disabled")).toBe(false);
    expect(
      (sipCard.getByRole("textbox", { name: "产品名称" }) as HTMLInputElement).value,
    ).toBe("上座");
    expect(
      (sipCard.getByRole("textbox", { name: "图号" }) as HTMLInputElement).value,
    ).toBe("JS26032501");
    expect(
      (sipCard.getByRole("textbox", { name: "版本号" }) as HTMLInputElement).value,
    ).toBe("A1");
    expect(
      (sipCard.getByRole("textbox", { name: "材质" }) as HTMLInputElement).value,
    ).toBe("SUS304");

    fireEvent.change(sipCard.getByRole("textbox", { name: "产品名称" }), {
      target: { value: "新上座" },
    });
    fireEvent.click(confirmMetadata);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "set_sip_metadata",
        material_code: "MAT-001",
        material_name: "新上座",
        drawing_number: "JS26032501",
        material: "SUS304",
        revision: "A1",
      });
      expect(summary.getByText("保存状态").nextElementSibling?.textContent)
        .toBe("已保存");
    });
  });

  test("尚未生成的 SIP 行不计入真实异常且不显示逐项空表单", () => {
    const items = [
      {
        item_id: "pending-sip-item",
        item_type: "thread" as const,
        raw_text: "M6",
        sip_detail_fields_confirmed: false,
        active: true,
      },
      {
        item_id: "ready-sip-item",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        sip_detail_fields_confirmed: true,
        active: true,
      },
    ];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "pending-sip-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const summary = within(screen.getByRole("region", { name: "项目摘要" }));
    expect(summary.getByText("SIP 表格").nextElementSibling?.textContent)
      .toBe("待生成 1 / 已生成 1 / 异常 0");
    openAuxiliaryPanel();
    const currentRegion = within(
      screen.getByRole("complementary", { name: "检验、导出与处理信息" }),
    ).getByRole("region", { name: "当前检验项" });
    expect(currentRegion.textContent).toContain("SIP 表格：待生成 1");
    expect(within(currentRegion).queryByRole("group", {
      name: "SIP 字段",
    })).toBeNull();
    expect(within(currentRegion).queryByRole("button", {
      name: "处理下一条异常",
    })).toBeNull();
  });

  test("完整图纸识别自动确认项目 SIP 信息", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={[
          metadataSuggestion("material_code", "12320096476"),
          metadataSuggestion("material_name", "横行滑板"),
          metadataSuggestion("drawing_number", "ZHZS25032501-04"),
          metadataSuggestion("material", "6061-T6"),
          metadataSuggestion("revision", "A/0"),
        ]}
        workingCopy={{
          id: "complete-suggestion-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {},
        }}
        onSave={onSave}
      />,
    );

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(onSave).toHaveBeenCalledWith({
      type: "set_sip_metadata",
      material_code: "12320096476",
      material_name: "横行滑板",
      drawing_number: "ZHZS25032501-04",
      material: "6061-T6",
      revision: "A/0",
    });
  });

  test("完整识别在命令通道恢复后只自动确认一次", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const workingCopy = {
      id: "busy-suggestion-working-copy",
      project_id: "project",
      raw_result_id: "raw",
      version: 1,
      items: [],
      coverage: { blocking_count: 0, review_required_count: 0 },
      numbering_stale: false,
      items_frozen_at: null,
      items_frozen_by: null,
      items_frozen_version: null,
      sip_metadata: {},
    };
    const suggestions = [
      metadataSuggestion("material_code", "12320096476"),
      metadataSuggestion("material_name", "横行滑板"),
      metadataSuggestion("drawing_number", "ZHZS25032501-04"),
      metadataSuggestion("material", "6061-T6"),
      metadataSuggestion("revision", "A/0"),
    ];
    const { rerender } = render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={suggestions}
        workingCopy={workingCopy}
        busy
        onSave={onSave}
      />,
    );

    expect(onSave).not.toHaveBeenCalled();
    rerender(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={suggestions}
        workingCopy={workingCopy}
        busy={false}
        onSave={onSave}
      />,
    );

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
  });

  test("识别值与已保存值冲突时不自动覆盖并要求人工检查", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={[
          metadataSuggestion("material_code", "12320096476"),
          metadataSuggestion("material_name", "识别产品名"),
          metadataSuggestion("drawing_number", "ZHZS25032501-04"),
          metadataSuggestion("material", "6061-T6"),
          metadataSuggestion("revision", "A/0"),
        ]}
        workingCopy={{
          id: "conflicting-suggestion-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: { material_name: "人工产品名" },
        }}
        onSave={onSave}
      />,
    );

    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
    expect(within(getSipRegion()).getByRole("status").textContent).toBe(
      "识别信息与已保存内容不一致，请检查后保存。",
    );
  });

  test("完整识别自动保存失败后不循环并允许显式重试", async () => {
    const onSave = vi.fn()
      .mockRejectedValueOnce(new Error("save failed"))
      .mockResolvedValueOnce(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={[
          metadataSuggestion("material_code", "12320096476"),
          metadataSuggestion("material_name", "横行滑板"),
          metadataSuggestion("drawing_number", "ZHZS25032501-04"),
          metadataSuggestion("material", "6061-T6"),
          metadataSuggestion("revision", "A/0"),
        ]}
        workingCopy={{
          id: "failed-suggestion-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {},
        }}
        onSave={onSave}
      />,
    );

    const sipRegion = getSipRegion();
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(within(sipRegion).getByRole("status").textContent).toBe(
      "项目 SIP 信息保存失败，请点击“保存项目 SIP 信息”重试。",
    );
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(onSave).toHaveBeenCalledOnce();

    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    fireEvent.click(within(sipRegion).getByRole("button", {
      name: "保存项目 SIP 信息",
    }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
  });

  test("项目 SIP 只要求补充缺失字段并通过既有命令保存", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={[
          {
            field: "material_code",
            value: "12320096476",
            observation_id: "material-code-value",
            label_observation_id: "material-code-label",
            page_index: 0,
            bbox_pdf: [1098.47, 807.02, 1152.38, 821.77],
            rule_version: "welli-title-metadata/1",
            evidence_codes: ["native_line"],
          },
          {
            field: "material_name",
            value: "横行滑板",
            observation_id: "material-name-value",
            label_observation_id: "drawing-number-label",
            page_index: 0,
            bbox_pdf: [1088.47, 739.28, 1121.92, 754.02],
            rule_version: "welli-title-metadata/1",
            evidence_codes: ["native_line"],
          },
          {
            field: "drawing_number",
            value: "ZHZS25032501-04",
            observation_id: "drawing-number-value",
            label_observation_id: "drawing-number-label",
            page_index: 0,
            bbox_pdf: [1088.29, 781.55, 1162.57, 796.3],
            rule_version: "welli-title-metadata/1",
            evidence_codes: ["native_line"],
          },
          {
            field: "revision",
            value: "A/0",
            observation_id: "revision-value",
            label_observation_id: "revision-label",
            page_index: 0,
            bbox_pdf: [821.55, 710.48, 839.54, 725.22],
            rule_version: "welli-title-metadata/1",
            evidence_codes: ["native_line"],
          },
        ]}
        workingCopy={{
          id: "suggestion-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {},
        }}
        onSave={onSave}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "物料编码",
      }) as HTMLInputElement
    ).value).toBe("12320096476");
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "产品名称",
      }) as HTMLInputElement
    ).value).toBe("横行滑板");
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "图号",
      }) as HTMLInputElement
    ).value).toBe("ZHZS25032501-04");
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "版本号",
      }) as HTMLInputElement
    ).value).toBe("A/0");
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "材质",
      }) as HTMLInputElement
    ).value).toBe("");
    expect(within(sipRegion).getByText(
      "系统已自动采纳 4/5，待补充：材质",
    )).not.toBeNull();
    expect(within(sipRegion).getAllByText("图纸识别，已自动采纳"))
      .toHaveLength(4);
    expect(onSave).not.toHaveBeenCalled();

    const confirm = within(sipRegion).getByRole("button", {
      name: "保存补充信息",
    });
    expect(confirm.hasAttribute("disabled")).toBe(true);
    fireEvent.change(within(sipRegion).getByRole("textbox", {
      name: "材质",
    }), { target: { value: "6061-T6" } });
    expect(within(sipRegion).getByRole("status").textContent).toBe(
      "信息已补全，请保存项目 SIP 信息。",
    );
    expect(confirm.textContent).toBe("保存项目 SIP 信息");
    fireEvent.click(confirm);

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "set_sip_metadata",
      material_code: "12320096476",
      material_name: "横行滑板",
      drawing_number: "ZHZS25032501-04",
      material: "6061-T6",
      revision: "A/0",
    }));
  });

  test("SIP 表格已生成后不重复显示生成入口并在异常修复后自动推进", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const sipItem = (
      itemId: string,
      rawText: string,
      confirmed: boolean,
    ) => ({
      item_id: itemId,
      item_type: "linear_dimension" as const,
      raw_text: rawText,
      status: "kept",
      balloon_required: true,
      requires_confirmation: false,
      sip_detail_fields_confirmed: confirmed,
      sip_mapping_exceptions: confirmed ? [] : ["missing_inspection_role"],
      inspection_item: `${rawText} 检验`,
      inspection_standard: "图纸要求",
      inspection_method: "卡尺",
      key_dimension: "是",
      inspection_role: "IPQC",
      source_page: 1,
      active: true,
    });
    const items = [
      sipItem("confirmed-item", "10", true),
      sipItem("pending-item-1", "20", false),
      sipItem("pending-item-2", "30", false),
    ];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "sip-progress-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "横行滑板",
            drawing_number: "ZHZS25032501-04",
            material: "6061-T6",
            revision: "A/0",
          },
        }}
        onSave={onSave}
      />,
    );

    const summary = within(
      screen.getByRole("region", { name: "项目摘要" }),
    );
    expect(summary.getByText("SIP 表格").nextElementSibling?.textContent)
      .toBe("已生成 1 / 异常 2");
    getSipRegion();
    expect(screen.getByText("SIP 表格：已生成 1，异常 2")).not.toBeNull();

    expect(screen.queryByRole("textbox", {
      name: "默认检验角色",
    })).toBeNull();
    expect(screen.queryByRole("button", {
      name: "生成并检查 SIP 表格",
    })).toBeNull();

    fireEvent.click(screen.getByRole("button", {
      name: "处理下一条异常",
    }));
    expect(screen.getByRole("textbox", { name: "检验项目：20" }))
      .not.toBeNull();

    fireEvent.click(screen.getByRole("button", {
      name: "解决并保存 SIP 异常",
    }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
        type: "set_sip_detail_fields",
        item_id: "pending-item-1",
      }));
      expect(screen.getByRole("textbox", { name: "检验项目：30" }))
        .not.toBeNull();
    });
  });

  test("已确认项目 SIP 优先于识别建议", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={[{
          field: "drawing_number",
          value: "SUGGESTED-DRAWING",
          observation_id: "drawing-number-value",
          label_observation_id: "drawing-number-label",
          page_index: 0,
          bbox_pdf: [1, 2, 3, 4],
          rule_version: "welli-title-metadata/1",
          evidence_codes: ["native_line"],
        }]}
        workingCopy={{
          id: "confirmed-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "CONFIRMED-MATERIAL",
            material_name: "已确认产品",
            drawing_number: "CONFIRMED-DRAWING",
            material: "SUS304",
            revision: "B1",
          },
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    expect((
      within(sipRegion).getByRole("textbox", {
        name: "图号",
      }) as HTMLInputElement
    ).value).toBe("CONFIRMED-DRAWING");
    expect(within(sipRegion).queryByText("图纸识别，待确认")).toBeNull();
  });

  test("识别建议刷新不覆盖未保存项目 SIP 草稿", () => {
    const suggestions = (materialName: string) => [{
      field: "material_name" as const,
      value: materialName,
      observation_id: "material-name-value",
      label_observation_id: "drawing-number-label",
      page_index: 0,
      bbox_pdf: [1, 2, 3, 4] as [number, number, number, number],
      rule_version: "welli-title-metadata/1" as const,
      evidence_codes: ["native_line"],
    }];
    const workbench = (version: number, materialName: string) => (
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        sipMetadataSuggestions={suggestions(materialName)}
        workingCopy={{
          id: "refresh-suggestion-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {},
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />
    );
    const { rerender } = render(workbench(1, "横行滑板"));
    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    fireEvent.change(productName, { target: { value: "人工修改名称" } });

    rerender(workbench(2, "刷新后的识别名称"));

    expect(productName.value).toBe("人工修改名称");
  });

  test("working copy 刷新不覆盖未保存 metadata 草稿且取消恢复最新基线", () => {
    const items = [{
      item_id: "metadata-item",
      item_type: "thread" as const,
      raw_text: "M6",
      active: true,
    }];
    const workbench = (version: number) => (
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: version === 1 ? 0 : 1,
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: version === 1 ? "上座" : "新版上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />
    );
    const { rerender } = render(workbench(1));

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    fireEvent.change(productName, {
      target: { value: "未保存新名称" },
    });
    expect(saveStatus.textContent).toBe("有未保存修改");

    rerender(workbench(2));

    expect(productName.value).toBe("未保存新名称");
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(within(sipRegion).getByRole("button", {
      name: "取消项目 SIP 信息修改",
    }));
    expect(productName.value).toBe("新版上座");
    expect(saveStatus.textContent).toBe("已保存");
  });

  test("metadata 保存失败保留草稿并允许原命令重试", async () => {
    const onSave = vi.fn()
      .mockRejectedValueOnce(new Error("save failed"))
      .mockResolvedValueOnce(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        onSave={onSave}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    const confirm = within(sipRegion).getByRole("button", {
      name: "保存项目 SIP 信息",
    });
    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    fireEvent.change(productName, { target: { value: "失败后重试名称" } });
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(saveStatus.textContent).toBe("保存失败");
    });
    expect(productName.value).toBe("失败后重试名称");

    fireEvent.click(confirm);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledTimes(2);
      expect(saveStatus.textContent).toBe("已保存");
    });
    expect(onSave).toHaveBeenNthCalledWith(1, {
      type: "set_sip_metadata",
      material_code: "MAT-001",
      material_name: "失败后重试名称",
      drawing_number: "JS26032501",
      material: "SUS304",
      revision: "A1",
    });
    expect(onSave).toHaveBeenNthCalledWith(2, {
      type: "set_sip_metadata",
      material_code: "MAT-001",
      material_name: "失败后重试名称",
      drawing_number: "JS26032501",
      material: "SUS304",
      revision: "A1",
    });
  });

  test("selected SIP 与待判定来源草稿分别保持未保存状态和切换草稿", () => {
    const items = [{
      item_id: "sip-item",
      item_type: "thread" as const,
      raw_text: "M16",
      inspection_item: "螺纹检验",
      inspection_standard: "GB/T 197",
      inspection_method: "螺纹规",
      key_dimension: "是",
      inspection_role: "检验员",
      source_page: 1,
      sip_detail_fields_confirmed: true,
      sip_mapping_exceptions: [],
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "pending-source",
          pageIndex: 0,
          bbox: [1, 2, 3, 4],
          rawText: "去除毛刺 2",
        }]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: 1,
            entries: [{
              observation_id: "pending-observation",
              source_location_id: "pending-source",
              candidate_id: null,
              disposition: "ambiguous",
              coordinates: [1, 2, 3, 4],
              requires_confirmation: true,
            }],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    getSipRegion();
    fireEvent.click(screen.getByRole("button", {
      name: "可选修改当前 SIP 行",
    }));
    fireEvent.change(screen.getByRole("textbox", {
      name: "检验方法：M16",
    }), { target: { value: "三针法复核" } });
    expect(saveStatus.textContent).toBe("有未保存修改");
    fireEvent.click(screen.getByRole("button", {
      name: "收起检验、导出与处理信息",
    }));
    openAuxiliaryPanel();
    expect((screen.getByRole("textbox", {
      name: "检验方法：M16",
    }) as HTMLInputElement).value).toBe("三针法复核");

    fireEvent.click(screen.getByRole("row", { name: /去除毛刺 2/ }));
    getSipRegion();
    const currentRegion = screen.getByRole("region", { name: "当前检验项" });
    expect(within(currentRegion).getByText("当前选择的是待判定来源。"))
      .not.toBeNull();
    expect(within(currentRegion).queryByRole("group", {
      name: "SIP 字段",
    })).toBeNull();
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
      target: { value: "去除全部毛刺" },
    });
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(screen.getByRole("row", { name: /M16/ }));
    expect(
      (screen.getByRole("textbox", {
        name: "检验方法：M16",
      }) as HTMLInputElement).value,
    ).toBe("三针法复核");
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(screen.getByRole("button", {
      name: "取消当前 SIP 字段修改",
    }));
    expect(
      (screen.getByRole("textbox", {
        name: "检验方法：M16",
      }) as HTMLInputElement).value,
    ).toBe("螺纹规");
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(screen.getByRole("row", { name: /去除毛刺 2/ }));
    expect(
      (screen.getByRole("textbox", {
        name: "原始标注",
      }) as HTMLInputElement).value,
    ).toBe("去除全部毛刺");
  });

  test.each([
    ["reviewed", "reviewed", null],
    ["frozen", "editing", "2026-07-27T10:00:00Z"],
  ])("%s 状态禁用项目和当前检验项 SIP fieldset", (
    _caseName,
    projectState,
    frozenAt,
  ) => {
    const items = [{
      item_id: "immutable-item",
      item_type: "thread" as const,
      raw_text: "M6",
      inspection_item: "螺纹检验",
      inspection_standard: "GB/T 197",
      inspection_method: "螺纹规",
      key_dimension: "是",
      inspection_role: "检验员",
      source_page: 1,
      sip_detail_fields_confirmed: true,
      sip_mapping_exceptions: [],
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: frozenAt,
          items_frozen_by: frozenAt === null ? null : "reviewer",
          items_frozen_version: frozenAt === null ? null : 1,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        projectState={projectState}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    expect((
      within(sipRegion).getByRole("group", {
        name: "编辑项目 SIP 信息",
      }) as HTMLFieldSetElement
    ).disabled).toBe(true);
    expect((within(screen.getByRole("region", {
      name: "当前检验项",
    })).getByRole("button", {
      name: "可选修改当前 SIP 行",
    }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("source-only coverage 从左侧列表选择并在右侧详情中处理", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const items = [{
      item_id: "item-1",
      item_type: "thread" as const,
      raw_text: "M6",
      balloon_required: true,
      requires_confirmation: false,
      active: true,
    }];
    const workingCopy: ReviewWorkingCopyView = {
      id: "hidden-working-id",
      project_id: "hidden-project-id",
      raw_result_id: "hidden-result-id",
      version: 4,
      items,
      coverage: {
        blocking_count: 0,
        review_required_count: 1,
        entries: [{
          observation_id: "hidden-observation-id",
          source_location_id: "hidden-source-id",
          candidate_id: null,
          disposition: "ambiguous",
          coordinates: [60, 70, 150, 84],
          requires_confirmation: true,
        }],
      },
      numbering_stale: false,
      items_frozen_at: null,
      items_frozen_by: null,
      items_frozen_version: null,
    };
    const view = render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "hidden-source-id",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "技术要求 2：去除毛刺",
        }]}
        balloons={[]}
        items={items}
        workingCopy={workingCopy}
        onSave={onSave}
      />,
    );

    expect(screen.queryByRole("region", { name: "来源待确认" })).toBeNull();
    const sourceRow = screen.getByRole("row", { name: /技术要求 2：去除毛刺/ });
    fireEvent.click(sourceRow);
    expect(screen.getByTestId("source-hidden-source-id").getAttribute("data-selected"))
      .toBe("true");
    expect(screen.queryByRole("region", { name: "所选检验项" })).toBeNull();
    const mergedWorkspace = screen.getByRole("group", {
      name: "检验项列表与编辑",
    });
    const listPane = mergedWorkspace.querySelector(
      ".inspection-review-workspace__list",
    ) as HTMLElement;
    const detailPane = mergedWorkspace.querySelector(
      ".inspection-review-workspace__detail",
    ) as HTMLElement;
    expect(within(listPane).queryByRole("group", {
      name: "待判定来源处理",
    })).toBeNull();
    expect(within(detailPane).getByRole("group", {
      name: "待判定来源处理",
    })).not.toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
      target: { value: "general_requirement" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加并生成气泡" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "promote_source",
        observation_id: "hidden-observation-id",
        raw_text: "技术要求 2：去除毛刺",
        item_type: "general_requirement",
        scope: "local_feature",
        balloon_required: true,
        page_index: 0,
      });
    });

    view.rerender(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "hidden-source-id",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "技术要求 2：去除毛刺",
        }]}
        balloons={[]}
        items={items}
        workingCopy={{
          ...workingCopy,
          version: 5,
          coverage: {
            blocking_count: 0,
            review_required_count: 0,
            entries: [],
          },
        }}
        onSave={onSave}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByRole("group", {
        name: "待判定来源处理",
      })).toBeNull();
      expect(screen.getByRole("region", { name: "审核命令" })).not.toBeNull();
      expect(screen.queryByText("当前选择的是待判定来源。")).toBeNull();
      expect(screen.getByTestId("source-hidden-source-id").getAttribute(
        "data-selected",
      )).toBe("false");
    });
  });

  test("legacy 待确认来源不再提供前台批量命令", () => {
    const onSave = vi.fn();
    const onPrepareReview = vi.fn().mockResolvedValue(undefined);
    const items = [{
      item_id: "item-1",
      item_type: "thread" as const,
      raw_text: "M6",
      balloon_required: true,
      requires_confirmation: false,
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[
          {
            id: "batch-source-1",
            pageIndex: 0,
            bbox: [10, 20, 30, 40],
            rawText: "设计 1",
          },
          {
            id: "batch-source-2",
            pageIndex: 0,
            bbox: [50, 60, 70, 80],
            rawText: "日期 2",
          },
        ]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "batch-working-id",
          project_id: "batch-project-id",
          raw_result_id: "batch-result-id",
          version: 8,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: 2,
            entries: [
              {
                observation_id: "batch-observation-1",
                source_location_id: "batch-source-1",
                candidate_id: null,
                disposition: "ambiguous",
                coordinates: [10, 20, 30, 40],
                requires_confirmation: true,
              },
              {
                observation_id: "batch-observation-2",
                source_location_id: "batch-source-2",
                candidate_id: null,
                disposition: "ambiguous",
                coordinates: [50, 60, 70, 80],
                requires_confirmation: true,
              },
            ],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
        onPrepareReview={onPrepareReview}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "确认当前有效项" }),
    ).toBeNull();
    expect(screen.getByRole("row", { name: /设计 1/ })).not.toBeNull();
    expect(onSave).not.toHaveBeenCalled();
    expect(onPrepareReview).not.toHaveBeenCalled();
  });

  test("黄色待判来源只展示含数字的原始来源", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[
          {
            id: "numeric-source",
            pageIndex: 0,
            bbox: [10, 20, 30, 40],
            rawText: "125 X 2",
          },
          {
            id: "text-source",
            pageIndex: 0,
            bbox: [50, 60, 70, 80],
            rawText: "贯穿",
          },
        ]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "numeric-source-working-id",
          project_id: "numeric-source-project-id",
          raw_result_id: "numeric-source-result-id",
          version: 1,
          items: [],
          coverage: {
            blocking_count: 0,
            review_required_count: 2,
            entries: [
              {
                observation_id: "numeric-observation",
                source_location_id: "numeric-source",
                candidate_id: null,
                disposition: "ambiguous",
                coordinates: [10, 20, 30, 40],
                requires_confirmation: true,
              },
              {
                observation_id: "text-observation",
                source_location_id: "text-source",
                candidate_id: null,
                disposition: "ambiguous",
                coordinates: [50, 60, 70, 80],
                requires_confirmation: true,
              },
            ],
          },
          technical_requirements: [{
            requirement_id: "text-requirement",
            ordinal: 1,
            raw_text: "贯穿",
            normalized_text: "贯穿",
            source_location_ids: ["text-source"],
            page_index: 0,
            category: "standalone_check",
            subtype: "through_feature",
            parsed_parameters: {},
            match_outcome: "unresolved",
            matched_candidate_ids: [],
            rule_version: "technical-requirement/1",
            review_required: true,
          }],
          manual_review_count: 2,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("row", {
      name: /125 X 2.*原始来源.*待判定来源/,
    })).not.toBeNull();
    expect(screen.queryByRole("row", {
      name: /贯穿.*原始来源.*待判定来源/,
    })).toBeNull();
    const textSourceOverlay = screen.getByTestId("source-text-source");
    fireEvent.click(textSourceOverlay);
    expect(textSourceOverlay.getAttribute("data-selected")).toBe("false");

    const technicalRequirements = screen.getByRole("region", {
      name: "技术要求匹配",
    });
    fireEvent.click(within(technicalRequirements).getByRole("button", {
      name: "展开技术要求",
    }));
    expect(within(technicalRequirements).getByText("贯穿")).not.toBeNull();
  });

  test("来源 promote 保存失败后保留选择和草稿供重试", async () => {
    const onSave = vi.fn().mockRejectedValue(new Error("save failed"));
    const items = [{
      item_id: "item-1",
      item_type: "thread" as const,
      raw_text: "M6",
      balloon_required: true,
      requires_confirmation: false,
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "retry-source-id",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "技术要求 2：去除毛刺",
        }]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "retry-working-id",
          project_id: "retry-project-id",
          raw_result_id: "retry-result-id",
          version: 4,
          items,
          coverage: {
            blocking_count: 0,
            review_required_count: 1,
            entries: [{
              observation_id: "retry-observation-id",
              source_location_id: "retry-source-id",
              candidate_id: null,
              disposition: "ambiguous",
              coordinates: [60, 70, 150, 84],
              requires_confirmation: true,
            }],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole("row", { name: /技术要求 2：去除毛刺/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
      target: { value: "技术要求：去除全部毛刺" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
      target: { value: "general_requirement" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加并生成气泡" }));

    await waitFor(() => {
      expect(within(
        screen.getByRole("region", { name: "项目摘要" }),
      ).getByRole("status").textContent).toBe("保存失败");
    });
    expect(onSave).toHaveBeenCalledWith({
      type: "promote_source",
      observation_id: "retry-observation-id",
      raw_text: "技术要求：去除全部毛刺",
      item_type: "general_requirement",
      scope: "local_feature",
      balloon_required: true,
      page_index: 0,
    });
    expect(screen.getByTestId("source-retry-source-id").getAttribute("data-selected"))
      .toBe("true");
    expect(
      (screen.getByRole("textbox", { name: "原始标注" }) as HTMLInputElement).value,
    ).toBe("技术要求：去除全部毛刺");
    expect(
      (screen.getByRole("combobox", { name: "检验类型" }) as HTMLSelectElement).value,
    ).toBe("general_requirement");
    expect(screen.getByRole("button", { name: "添加并生成气泡" })
      .hasAttribute("disabled")).toBe(false);
  });

  test("workbench 不把空白来源显示为待判来源", () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[{
          id: "blank-source-id",
          pageIndex: 0,
          bbox: [1, 2, 3, 4],
          rawText: "   ",
        }]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "blank-working-id",
          project_id: "blank-project-id",
          raw_result_id: "blank-result-id",
          version: 1,
          items: [],
          coverage: {
            blocking_count: 0,
            review_required_count: 1,
            entries: [{
              observation_id: "blank-observation-id",
              source_location_id: "blank-source-id",
              candidate_id: null,
              disposition: "ambiguous",
              coordinates: [1, 2, 3, 4],
              requires_confirmation: true,
            }],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    expect(screen.queryByRole("row", {
      name: /原始来源.*待判定来源/,
    })).toBeNull();
    expect(onSave).not.toHaveBeenCalled();
  });

  test("自动通过项可选择编辑且列表与详情不显示置信度内部元数据", () => {
    const items = [
      {
        item_id: "auto-item",
        item_type: "linear_dimension" as const,
        raw_text: "10",
        nominal: "10",
        status: "auto_accepted",
        balloon_required: true,
        requires_confirmation: false,
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
        item_id: "review-item",
        item_type: "linear_dimension" as const,
        raw_text: "20",
        nominal: "20",
        status: "pending",
        confidence_decision: {
          band: "medium" as const,
          review_disposition: "review_required" as const,
          policy_version: "candidate-confidence/1" as const,
          evidence_codes: ["coverage_unchecked"],
        },
        active: true,
      },
      {
        item_id: "kept-confirmation-item",
        item_type: "linear_dimension" as const,
        raw_text: "25",
        nominal: "25",
        status: "kept",
        requires_confirmation: true,
        active: true,
      },
    ];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          manual_review_count: 2,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("button", { name: "筛选全部" })
      .getAttribute("data-active")).toBe("true");
    expect(screen.getByRole("row", { name: /10/ })).not.toBeNull();
    expect(screen.getByRole("row", { name: /20/ })).not.toBeNull();
    expect(screen.getByRole("row", { name: /25/ })).not.toBeNull();

    const autoAcceptedRow = screen.getByRole("row", { name: /10/ });
    expect(autoAcceptedRow.textContent).toContain("自动通过");
    fireEvent.click(autoAcceptedRow);
    expect(screen.getByRole("textbox", { name: "基本尺寸：10" })).not.toBeNull();
    expect(screen.queryByText("高置信度")).toBeNull();
    expect(screen.queryByText("candidate-confidence/1")).toBeNull();
    expect(screen.queryByText("typed_schema_complete")).toBeNull();
  });

  test("全自动通过结果在默认全部筛选中可直接选择编辑", () => {
    const items = [{
      item_id: "only-auto-item",
      item_type: "linear_dimension" as const,
      raw_text: "30",
      nominal: "30",
      status: "auto_accepted",
      requires_confirmation: false,
      acceptance_source: "confidence_policy" as const,
      confidence_decision: {
        band: "high" as const,
        review_disposition: "auto_accepted" as const,
        policy_version: "candidate-confidence/1" as const,
        evidence_codes: ["typed_schema_complete"],
      },
      balloon_required: true,
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "all-high-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          manual_review_count: 0,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("button", { name: "筛选全部" })
      .getAttribute("data-active")).toBe("true");
    expect(screen.queryByRole("article", {
      name: /检验项/,
    })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "基本尺寸：30" })).toBeNull();

    const row = screen.getByRole("row", { name: /30/ });
    expect(row.getAttribute("data-selected")).toBe("false");
    fireEvent.click(row);

    expect(screen.getByRole("textbox", { name: "基本尺寸：30" })).not.toBeNull();
    expect(screen.getByRole("article", {
      name: "检验项 — · 线性尺寸",
    })).not.toBeNull();
  });

  test("技术要求面板复用唯一保存命令 seam", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const items = [{
      item_id: "dimension-25",
      item_type: "linear_dimension" as const,
      raw_text: "25",
      nominal: "25",
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "technical-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 1 },
          technical_requirements: [{
            requirement_id: "requirement-5",
            ordinal: 5,
            raw_text: "未注尺寸公差按 GB/T 1804-m 执行",
            normalized_text: "未注尺寸公差按 GB/T 1804-m 执行",
            source_location_ids: ["source-5"],
            page_index: 0,
            category: "applicability_rule",
            subtype: "general_dimensional_tolerance",
            parsed_parameters: {},
            match_outcome: "unresolved",
            matched_candidate_ids: [],
            rule_version: "technical-requirement/1",
            review_required: true,
          }],
          manual_review_count: 1,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    expect(screen.getByRole("region", { name: "检验项审核" }).classList.contains(
      "inspection-pane--with-technical-requirements",
    )).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
    fireEvent.click(screen.getByRole("radio", {
      name: "只应用到部分检验项",
    }));
    fireEvent.click(screen.getByRole("checkbox", { name: "25" }));
    fireEvent.click(screen.getByRole("button", {
      name: "确认并处理下一条",
    }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "set_technical_requirement_match",
      requirement_id: "requirement-5",
      outcome: "matched_items",
      matched_item_ids: ["dimension-25"],
    }));
  });

  test("技术要求匹配项跳转会从其他筛选恢复全部并选中目标", () => {
    const items = [{
      item_id: "auto-dimension-100",
      item_type: "linear_dimension" as const,
      raw_text: "100",
      nominal: "100",
      status: "auto_accepted",
      requires_confirmation: false,
      acceptance_source: "confidence_policy" as const,
      confidence_decision: {
        band: "high" as const,
        review_disposition: "auto_accepted" as const,
        policy_version: "candidate-confidence/1" as const,
        evidence_codes: ["typed_schema_complete"],
      },
      balloon_required: true,
      active: true,
    }];
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={items}
        workingCopy={{
          id: "technical-navigation-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items,
          coverage: { blocking_count: 0, review_required_count: 0 },
          technical_requirements: [{
            requirement_id: "requirement-5",
            ordinal: 5,
            raw_text: "未注尺寸公差按 GB/T 1804-m 执行",
            normalized_text: "未注尺寸公差按 GB/T 1804-m 执行",
            source_location_ids: ["source-5"],
            page_index: 0,
            category: "applicability_rule",
            subtype: "general_dimensional_tolerance",
            parsed_parameters: {},
            match_outcome: "matched_items",
            matched_candidate_ids: ["auto-dimension-100"],
            rule_version: "technical-requirement/1",
            review_required: true,
          }],
          manual_review_count: 0,
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("button", { name: "筛选全部" })
      .getAttribute("data-active")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "筛选待人工审核" }));
    expect(screen.getByRole("button", { name: "筛选待人工审核" })
      .getAttribute("data-active")).toBe("true");
    expect(screen.queryByRole("row", { name: /100/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
    fireEvent.click(screen.getByRole("button", {
      name: "查看系统建议关联项（1 项）",
    }));

    expect(screen.getByRole("button", { name: "筛选全部" })
      .getAttribute("data-active")).toBe("true");
    expect(screen.getByRole("row", { name: /100/ })
      .getAttribute("data-selected")).toBe("true");
  });

  test("有草稿时返回列表提供保存、不保存和取消三种选择", () => {
    const onReset = vi.fn();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "return-dialog-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        onSave={onSave}
        onReset={onReset}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    fireEvent.change(productName, { target: { value: "未保存名称" } });
    fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));

    const dialog = screen.getByRole("dialog", { name: "返回图纸列表？" });
    expect(within(dialog).getByRole("button", { name: "保存并返回" }))
      .toBe(document.activeElement);
    expect(within(dialog).getByRole("button", { name: "不保存返回" }))
      .not.toBeNull();
    expect(within(dialog).getByRole("button", { name: "取消" })).not.toBeNull();

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(productName.value).toBe("未保存名称");
    expect(onReset).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
    fireEvent.click(screen.getByRole("button", { name: "不保存返回" }));
    expect(onReset).toHaveBeenCalledOnce();
    expect(onSave).not.toHaveBeenCalled();
  });

  test("保存并返回失败时留在工作台并保留草稿", async () => {
    const onReset = vi.fn();
    const onSave = vi.fn().mockRejectedValue(new Error("save failed"));
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "return-failed-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        onSave={onSave}
        onReset={onReset}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    fireEvent.change(productName, { target: { value: "失败后保留" } });
    fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
    fireEvent.click(screen.getByRole("button", { name: "保存并返回" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    expect(screen.getByRole("dialog", { name: "返回图纸列表？" }))
      .not.toBeNull();
    expect(productName.value).toBe("失败后保留");
    expect(onReset).not.toHaveBeenCalled();
  });

  test("全部草稿保存成功后才返回列表", async () => {
    const onReset = vi.fn();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={{
          id: "return-success-working-copy",
          project_id: "project",
          raw_result_id: "raw",
          version: 1,
          items: [],
          coverage: { blocking_count: 0, review_required_count: 0 },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
          sip_metadata: {
            material_code: "MAT-001",
            material_name: "上座",
            drawing_number: "JS26032501",
            material: "SUS304",
            revision: "A1",
          },
        }}
        onSave={onSave}
        onReset={onReset}
      />,
    );

    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    fireEvent.change(within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }), { target: { value: "保存后返回" } });
    fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
    fireEvent.click(screen.getByRole("button", { name: "保存并返回" }));

    await waitFor(() => expect(onReset).toHaveBeenCalledOnce());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      type: "set_sip_metadata",
      material_name: "保存后返回",
    }));
  });

  test("技术要求草稿阻止自动准备，并通过保存返回门禁提交", async () => {
    const onReset = vi.fn();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onPrepareReview = vi.fn().mockResolvedValue(undefined);
    const workingCopy: ReviewWorkingCopyView = {
      id: "technical-requirement-draft-working-copy",
      project_id: "project",
      raw_result_id: "raw",
      version: 1,
      items: [],
      coverage: { blocking_count: 0, review_required_count: 0 },
      technical_requirements: [{
        requirement_id: "global-requirement",
        ordinal: 1,
        raw_text: "锐边去毛刺",
        normalized_text: "锐边去毛刺",
        source_location_ids: ["source-global"],
        page_index: 0,
        category: "standalone_check",
        subtype: "deburr",
        parsed_parameters: {},
        match_outcome: "global_scope",
        matched_candidate_ids: [],
        generated_candidate_id: "global-deburr",
        rule_version: "technical-requirement/1",
        review_required: false,
        review_status: "confirmed",
      }],
      numbering_stale: false,
      items_frozen_at: null,
      items_frozen_by: null,
      items_frozen_version: null,
      sip_metadata: {
        material_code: "MAT-001",
        material_name: "上座",
        drawing_number: "JS26032501",
        material: "SUS304",
        revision: "A1",
      },
    };
    const view = render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={workingCopy}
        onSave={onSave}
        onReset={onReset}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "展开技术要求" }));
    fireEvent.click(screen.getByRole("button", { name: "修改" }));
    fireEvent.click(screen.getByRole("button", { name: "更改处理方式" }));
    fireEvent.click(screen.getByRole("radio", { name: "排除此要求" }));
    const sipRegion = getSipRegion();
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    fireEvent.change(within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }), { target: { value: "技术要求联动草稿" } });

    view.rerender(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={[]}
        workingCopy={workingCopy}
        onSave={onSave}
        onReset={onReset}
        onPrepareReview={onPrepareReview}
      />,
    );
    expect(onPrepareReview).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
    expect(screen.getByRole("dialog", { name: "返回图纸列表？" }))
      .not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保存并返回" }));

    await waitFor(() => expect(onReset).toHaveBeenCalledOnce());
    expect(onSave).toHaveBeenNthCalledWith(1, {
      type: "set_technical_requirement_match",
      requirement_id: "global-requirement",
      outcome: "excluded",
    });
    expect(onSave).toHaveBeenNthCalledWith(2, expect.objectContaining({
      type: "set_sip_metadata",
      material_name: "技术要求联动草稿",
    }));
    expect(onPrepareReview).not.toHaveBeenCalled();
  });
});
