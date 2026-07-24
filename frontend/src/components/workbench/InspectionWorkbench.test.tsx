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
    name: "展开 SIP 与导出信息",
  }));
}

describe("InspectionWorkbench", () => {
  test("本地草稿立即显示未保存，取消后恢复真实保存状态", () => {
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
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    expect(saveStatus.textContent).toBe("已保存");

    fireEvent.change(screen.getByRole("textbox", { name: "原始标注：M6" }), {
      target: { value: "M8" },
    });

    expect(saveStatus.textContent).toBe("有未保存修改");
    expect(screen.getByRole("button", { name: "保存审核修改" })
      .hasAttribute("disabled")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "取消检验项修改：M6" }));
    expect(
      (screen.getByRole("textbox", { name: "原始标注：M6" }) as HTMLInputElement)
        .value,
    ).toBe("M6");
    expect(saveStatus.textContent).toBe("已保存");
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
    expect(screen.getByRole("region", { name: "审核流程操作" }).textContent)
      .not.toContain("审核修改已提交");
  });

  test("项目摘要后保留审核操作且不重复全局头部", () => {
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
    const reviewActions = screen.getByRole("region", { name: "审核流程操作" });
    const children = Array.from(shell.children);

    expect(children.indexOf(projectSummary)).toBeLessThan(
      children.indexOf(reviewActions),
    );
    expect(screen.queryByText("工程图纸检验工作台")).toBeNull();
    expect(screen.queryByRole("heading", { name: "检验项目审核" })).toBeNull();
    expect(screen.getByRole("button", { name: "保存审核修改" })).not.toBeNull();
  });

  test("P0-UI-007 keeps one pending command stable until explicit Save", async () => {
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

    fireEvent.click(screen.getByRole("row", { name: /M6/ }));
    fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));

    expect(screen.getByText("有未保存修改")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "排除检验项：M6" }).getAttribute("disabled"),
    ).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "排除检验项：M6" }));
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "保存审核修改" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({ type: "keep", item_id: "i1" });
      expect(screen.getByText("已保存")).not.toBeNull();
    });
    expect(
      screen.getByRole("button", { name: "排除检验项：M6" }).getAttribute("disabled"),
    ).toBeNull();
  });

  test("P0-UI-007 submits Save only once while the request is in flight", async () => {
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
    fireEvent.click(screen.getByRole("row", { name: /M6/ }));
    fireEvent.click(screen.getByRole("button", { name: "保留检验项：M6" }));
    const save = screen.getByRole("button", { name: "保存审核修改" });

    fireEvent.click(save);
    fireEvent.click(save);

    expect(save.getAttribute("disabled")).not.toBeNull();
    expect(onSave).toHaveBeenCalledOnce();

    resolveSave();
    await waitFor(() => expect(screen.getByText("已保存")).not.toBeNull());
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
    expect(screen.queryByRole("complementary", { name: "SIP 与导出信息" }))
      .toBeNull();
    const workspaceButton = screen.getByRole("button", {
      name: "展开 SIP 与导出信息",
    });
    expect(workspaceButton.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(workspaceButton);

    expect(workspaceButton.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("complementary", { name: "SIP 与导出信息" }))
      .not.toBeNull();
    expect(screen.getByText("公司处理记录")).not.toBeNull();
    expect(screen.getByText("暂无处理记录")).not.toBeNull();
    expect(document.body.textContent).not.toContain("hidden-project-uuid");
    expect(document.body.textContent).not.toContain("hidden-operator-uuid");
    expect(document.body.textContent).not.toContain("hidden-item-uuid");
    expect(document.body.textContent).not.toContain("自动保存");
    const actionLabels = screen.getAllByRole("button")
      .map((button) => button.textContent?.trim())
      .filter((label) => [
        "保存审核修改",
        "冻结检验项",
        "生成气泡",
        "确认审核结果",
        "生成正式文件",
      ].includes(label ?? ""));
    expect(actionLabels).toEqual([
      "保存审核修改",
      "冻结检验项",
      "生成气泡",
      "确认审核结果",
      "生成正式文件",
    ]);
  });

  test("编辑所选检验项时持续显示真实编号、页码、状态和原始标注", () => {
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

    const selectedSummary = screen.getByRole("region", {
      name: "所选检验项",
    });
    for (const value of ["17", "M8", "第 2 页", "已确认"]) {
      expect(selectedSummary.textContent).toContain(value);
    }
    expect(selectedSummary.textContent).not.toContain("selected-hidden-uuid");
    expect(
      (screen.getByRole("textbox", {
        name: "原始标注：M8",
      }) as HTMLInputElement).value,
    ).toBe("M8");
  });

  test("正式导出完成时紧凑显示 SIP 基本信息及三份真实下载", () => {
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
      name: "SIP 与导出信息",
    });
    const exportRegion = screen.getByRole("region", {
      name: "正式文件导出",
    });
    const sipRegion = screen.getByRole("region", { name: "SIP基本信息" });
    expect(aside.firstElementChild).toBe(sipRegion);
    expect(sipRegion.nextElementSibling).toBe(exportRegion);
    expect(
      within(exportRegion).getAllByRole("link").map((link) => link.textContent),
    ).toEqual([
      "下载带气泡 PDF",
      "下载 SIP Excel",
      "下载校验清单",
    ]);

    const summary = sipRegion.querySelector("dl");
    expect(summary).not.toBeNull();
    expect(summary?.textContent).toContain("产品名称上座");
    expect(summary?.textContent).toContain("图号JS26032501");
    const editor = sipRegion.querySelector("details");
    expect(editor?.hasAttribute("open")).toBe(false);
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
      name: "收起 SIP 与导出信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开 SIP 与导出信息",
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
      name: "收起 SIP 与导出信息",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "展开 SIP 与导出信息",
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
        inspection_standard: "GB/T 197",
        inspection_role: "尺寸检验员",
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

    openAuxiliaryPanel();

    const sipRegion = screen.getByRole("region", { name: "SIP基本信息" });
    const sipSummary = sipRegion.querySelector("dl");
    expect(sipSummary).not.toBeNull();
    const sipCard = within(sipRegion);
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

    const editorSummary = sipRegion.querySelector("summary");
    expect(editorSummary?.textContent).toBe("编辑 SIP 信息");
    fireEvent.click(editorSummary as HTMLElement);
    const confirmMetadata = sipCard.getByRole("button", { name: "确认 SIP 信息" });
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
    expect(summary.getByText("保存状态").nextElementSibling?.textContent)
      .toBe("有未保存修改");
    fireEvent.click(screen.getByRole("button", { name: "保存审核修改" }));

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

  test("source-only coverage 可通过中文审核入口保存并解除冻结前置项", async () => {
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

    expect(screen.getByRole("region", { name: "来源待确认" }).textContent)
      .toContain("技术要求：去除毛刺");
    expect(
      screen.getByRole("region", { name: "来源待确认" })
        .compareDocumentPosition(screen.getByRole("table", { name: "检验项列表" }))
        & Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0);
    expect(screen.getByTestId("source-hidden-source-id").getAttribute("data-selected"))
      .toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "确认保留此来源" }));
    fireEvent.click(screen.getByRole("button", { name: "保存审核修改" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "resolve_confirmation",
        item_id: "hidden-observation-id",
        accepted: true,
      });
    });
    expect(document.body.textContent).not.toContain("hidden-observation-id");
    expect(document.body.textContent).not.toContain("hidden-source-id");
  });
});
