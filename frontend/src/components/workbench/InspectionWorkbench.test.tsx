import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { PostJson } from "../../api/types";
import { InspectionWorkbench } from "./InspectionWorkbench";


afterEach(cleanup);

function openAuxiliaryPanel(): void {
  fireEvent.click(screen.getByRole("button", {
    name: "展开导出与处理信息",
  }));
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
          rawText: "来源待判定",
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
          rawText: "来源待判定",
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
    const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
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
    const projectSummary = screen.getByRole("region", { name: "项目摘要" });
    const children = Array.from(shell.children);

    expect(children.indexOf(projectSummary)).toBe(0);
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
        onFreeze={vi.fn()}
        onGenerate={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    const projectSummary = screen.getByRole("region", { name: "项目摘要" });
    for (const value of ["上座", "JS26032501", "A1"]) {
      expect(projectSummary.textContent).toContain(value);
    }
    expect(screen.getByRole("region", { name: "工程图纸" })).not.toBeNull();
    expect(screen.getByRole("region", { name: "检验项审核" })).not.toBeNull();
    expect(screen.queryByRole("complementary", { name: "导出与处理信息" }))
      .toBeNull();
    const workspaceButton = screen.getByRole("button", {
      name: "展开导出与处理信息",
    });
    expect(workspaceButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(workspaceButton);

    expect(workspaceButton.getAttribute("aria-expanded")).toBe("true");
    const aside = screen.getByRole("complementary", {
      name: "导出与处理信息",
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
    expect(actionLabels).toEqual([
      "冻结检验项",
      "生成气泡",
      "确认审核结果",
      "生成正式文件",
    ]);
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
          active: true,
        }]}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onDeleteBalloon={vi.fn()}
        onRebuildBalloon={vi.fn()}
        onReorderBalloon={vi.fn()}
        onRenumberBalloons={vi.fn()}
      />,
    );

    const reviewRegion = screen.getByRole("region", { name: "检验项审核" });
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
            active: true,
          },
        ]}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

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

  test("正式导出完成时辅助区只显示导出与处理信息", () => {
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
        initialExport={{
          id: "export-success",
          project_id: "project-1",
          reviewed_result_id: "reviewed-1",
          status: "success",
          artifacts: [
            { kind: "ballooned_pdf", downloadable: true },
            { kind: "sip_excel", downloadable: true },
            { kind: "manifest", downloadable: true },
          ],
        }}
        exportPost={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    openAuxiliaryPanel();

    const aside = screen.getByRole("complementary", {
      name: "导出与处理信息",
    });
    const exportRegion = screen.getByRole("region", {
      name: "正式文件导出",
    });
    expect(within(aside).queryByRole("region", { name: "SIP基本信息" }))
      .toBeNull();
    expect(aside.firstElementChild).toBe(exportRegion);
    expect(
      within(exportRegion).getAllByRole("link").map((link) => link.textContent),
    ).toEqual([
      "下载带气泡 PDF",
      "下载 SIP Excel",
      "下载校验清单",
    ]);
  });

  test("生成正式文件后收起再展开仍保留三份下载", async () => {
    const exportPost = vi.fn().mockResolvedValue({
      id: "export-success",
      project_id: "project-1",
      reviewed_result_id: "reviewed-1",
      status: "success",
      artifacts: [
        { kind: "ballooned_pdf", downloadable: true },
        { kind: "sip_excel", downloadable: true },
        { kind: "manifest", downloadable: true },
      ],
    });
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
      name: "收起导出与处理信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开导出与处理信息",
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
    fireEvent.click(screen.getByRole("button", {
      name: "收起导出与处理信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开导出与处理信息",
    }));

    const exportButton = screen.getByRole("button", { name: "生成正式文件" });
    expect(exportButton.hasAttribute("disabled")).toBe(true);
    fireEvent.click(exportButton);
    expect(exportPost).toHaveBeenCalledOnce();

    resolveExport({
      id: "export-success",
      project_id: "project-1",
      reviewed_result_id: "reviewed-1",
      status: "success",
      artifacts: [
        { kind: "ballooned_pdf", downloadable: true },
        { kind: "sip_excel", downloadable: true },
        { kind: "manifest", downloadable: true },
      ],
    });
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

    const summary = within(
      screen.getByRole("region", { name: "项目摘要" }),
    );
    expect(summary.getByText("已审核").nextElementSibling?.textContent).toBe("1");
    expect(summary.getByText("已确认").nextElementSibling?.textContent).toBe("1");
    expect(summary.getByText("保存状态").nextElementSibling?.textContent)
      .toBe("已保存");

    expect(screen.getAllByRole("region", { name: "SIP 信息" })).toHaveLength(1);
    const detail = container.querySelector(
      ".inspection-review-workspace__detail",
    ) as HTMLElement;
    const sipRegion = within(detail).getByRole("region", { name: "SIP 信息" });
    expect(detail.querySelector(".review-panel")?.nextElementSibling)
      .toBe(sipRegion);
    const projectRegion = within(sipRegion).getByRole("region", {
      name: "项目基本信息",
    });
    const currentRegion = within(sipRegion).getByRole("region", {
      name: "当前检验项",
    });
    const sipSummary = projectRegion.querySelector("dl");
    expect(sipSummary).not.toBeNull();
    const sipCard = within(projectRegion);
    for (const label of [
      "产品名称",
      "图号",
      "版本号",
      "材质",
      "单位",
      "检验标准",
      "检验人员角色",
      "审核人员角色",
    ]) {
      expect(sipSummary?.textContent).toContain(label);
    }
    expect(sipSummary?.textContent).not.toContain("物料编码");
    expect(sipSummary?.textContent).toContain("产品名称上座");
    expect(sipSummary?.textContent).toContain("图号JS26032501");
    expect(sipSummary?.textContent).toContain("版本号A1");
    expect(sipSummary?.textContent).toContain("材质SUS304");
    expect(sipSummary?.textContent).toContain("检验标准GB/T 197");
    expect(sipSummary?.textContent).toContain("检验人员角色尺寸检验员");
    expect(sipSummary?.querySelectorAll("dd")).toHaveLength(8);
    const selectedFields = within(currentRegion).getByRole("group", {
      name: "SIP 确认字段",
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
      name: "确认项目 SIP 信息",
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

    const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
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

    const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    const productName = within(sipRegion).getByRole("textbox", {
      name: "产品名称",
    }) as HTMLInputElement;
    const confirm = within(sipRegion).getByRole("button", {
      name: "确认项目 SIP 信息",
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
          rawText: "去除毛刺",
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
    fireEvent.change(screen.getByRole("textbox", {
      name: "检验方法：M16",
    }), { target: { value: "三针法复核" } });
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(screen.getByRole("row", { name: /去除毛刺/ }));
    const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
    expect(within(sipRegion).getByText("当前选择的是待判定来源。"))
      .not.toBeNull();
    expect(within(sipRegion).queryByRole("group", {
      name: "SIP 确认字段",
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
      name: "取消当前检验项 SIP 修改",
    }));
    expect(
      (screen.getByRole("textbox", {
        name: "检验方法：M16",
      }) as HTMLInputElement).value,
    ).toBe("螺纹规");
    expect(saveStatus.textContent).toBe("有未保存修改");

    fireEvent.click(screen.getByRole("row", { name: /去除毛刺/ }));
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

    const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
    fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
      selector: "summary",
    }));
    expect((
      within(sipRegion).getByRole("group", {
        name: "编辑项目 SIP 信息",
      }) as HTMLFieldSetElement
    ).disabled).toBe(true);
    expect((
      within(sipRegion).getByRole("group", {
        name: "SIP 确认字段",
      }) as HTMLFieldSetElement
    ).disabled).toBe(true);
  });

  test("source-only coverage 在统一列表中添加为真实检验项并保存", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
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
          id: "hidden-source-id",
          pageIndex: 0,
          bbox: [60, 70, 150, 84],
          rawText: "技术要求：去除毛刺",
        }]}
        balloons={[]}
        items={items}
        workingCopy={{
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
        }}
        onSave={onSave}
        onFreeze={vi.fn()}
        onGenerate={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.queryByRole("region", { name: "来源待确认" })).toBeNull();
    const sourceRow = screen.getByRole("row", { name: /技术要求：去除毛刺/ });
    fireEvent.click(sourceRow);
    expect(screen.getByTestId("source-hidden-source-id").getAttribute("data-selected"))
      .toBe("true");
    expect(screen.queryByRole("region", { name: "所选检验项" })).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
      target: { value: "general_requirement" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "promote_source",
        observation_id: "hidden-observation-id",
        raw_text: "技术要求：去除毛刺",
        item_type: "general_requirement",
        scope: "local_feature",
        balloon_required: true,
        page_index: 0,
      });
    });
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
          rawText: "技术要求：去除毛刺",
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

    fireEvent.click(screen.getByRole("row", { name: /技术要求：去除毛刺/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
      target: { value: "技术要求：去除全部毛刺" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
      target: { value: "general_requirement" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));

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
    expect(screen.getByRole("button", { name: "添加为检验项" })
      .hasAttribute("disabled")).toBe(false);
  });

  test("workbench 不把空白来源的显示占位符传入 promote 草稿", async () => {
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

    fireEvent.click(screen.getByRole("row", {
      name: /原始来源.*待判定来源/,
    }));
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
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "promote_source",
      observation_id: "blank-observation-id",
      raw_text: "人工补录的真实要求",
      item_type: "general_requirement",
      scope: "local_feature",
      balloon_required: true,
      page_index: 0,
    }));
  });
});
