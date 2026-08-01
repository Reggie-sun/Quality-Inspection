import { createRef } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ReviewItem } from "../../api/types";
import type { DraftSaveHandle } from "./draftSave";
import {
  SipInformationPanel,
  type MetadataDraft,
} from "./SipInformationPanel";


afterEach(cleanup);

const metadata: MetadataDraft = {
  material_code: "MAT-001",
  material_name: "上座",
  drawing_number: "JS26032501",
  material: "SUS304",
  revision: "A1",
};

const metadataValues = [
  ["产品名称", "上座"],
  ["图号", "JS26032501"],
  ["单位", undefined],
] as const;

function reviewItem(overrides: Partial<ReviewItem> = {}): ReviewItem {
  return {
    item_id: "item-1",
    raw_text: "M6",
    item_type: "thread",
    inspection_item: "螺纹检验",
    inspection_standard: "GB/T 197",
    inspection_method: "螺纹规",
    key_dimension: "是",
    inspection_role: "检验员",
    source_page: 1,
    remarks: "",
    active: true,
    ...overrides,
  };
}

function panelProps(
  overrides: Partial<React.ComponentProps<typeof SipInformationPanel>> = {},
) {
  return {
    metadata,
    metadataValues,
    metadataConfirmed: true,
    metadataDirty: false,
    disabled: false,
    selectedItem: reviewItem(),
    pendingItemCount: 1,
    onMetadataChange: vi.fn(),
    onConfirmMetadata: vi.fn(),
    onCancelMetadata: vi.fn(),
    onCommand: vi.fn(),
    ...overrides,
  };
}

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof SipInformationPanel>> = {},
) {
  return render(<SipInformationPanel {...panelProps(overrides)} />);
}

test("待生成状态不常驻渲染当前检验项 SIP 表单", () => {
  renderPanel();

  const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
  const currentRegion = screen.getByRole("region", { name: "当前检验项" });
  expect(within(sipRegion).getByRole("heading", {
    level: 2,
    name: "SIP 信息",
  })).toBeTruthy();
  expect(within(sipRegion).getByRole("heading", {
    level: 3,
    name: "项目基本信息",
  })).toBeTruthy();
  expect(within(currentRegion).getByRole("heading", {
    level: 3,
    name: "当前检验项",
  })).toBeTruthy();
  expect(within(currentRegion).queryByRole("group", {
    name: "SIP 字段",
  })).toBeNull();
  expect(currentRegion.textContent).toContain("请先生成 SIP 表格");
  expect(sipRegion.contains(currentRegion)).toBe(false);
  expect(sipRegion.textContent).toContain("产品名称上座");
  expect(sipRegion.textContent).toContain("图号JS26032501");
  expect(sipRegion.textContent).toContain("单位—");
});

test("切到待判定来源时保留真实异常的当前检验项草稿", () => {
  const props = panelProps({
    pendingItemCount: 0,
    exceptionItemCount: 1,
    selectedItem: reviewItem({
      sip_detail_fields_confirmed: false,
      sip_mapping_exceptions: ["composite_method_required"],
    }),
  });
  const { rerender } = render(<SipInformationPanel {...props} />);

  expect(screen.queryByRole("textbox", {
    name: "默认检验角色",
  })).toBeNull();
  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M6" }), {
    target: { value: "三针法复核" },
  });
  rerender(<SipInformationPanel {...props} selectedSourceActive />);

  const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
  const currentRegion = screen.getByRole("region", { name: "当前检验项" });
  expect(within(sipRegion).getByRole("heading", {
    level: 3,
    name: "项目基本信息",
  })).toBeTruthy();
  expect(sipRegion.textContent).toContain("产品名称上座");
  expect(currentRegion.textContent).toContain("当前选择的是待判定来源。");
  expect(within(currentRegion).queryByRole("group", {
    name: "SIP 字段",
  })).toBeNull();

  rerender(<SipInformationPanel {...props} selectedSourceActive={false} />);
  expect(
    (screen.getByRole("textbox", {
      name: "检验方法：M6",
    }) as HTMLInputElement).value,
  ).toBe("三针法复核");
});

test("项目 SIP 信息不完整时禁用保存，补全后启用", () => {
  const incompleteMetadata = { ...metadata, material_code: "" };
  const props = panelProps({
    metadata: incompleteMetadata,
    metadataConfirmed: false,
    missingMetadataFields: ["物料编码"],
  });
  const { rerender } = render(<SipInformationPanel {...props} />);

  const confirm = screen.getByRole("button", {
    name: "保存补充信息",
  });
  expect(confirm.hasAttribute("disabled")).toBe(true);

  rerender(<SipInformationPanel {...props} metadata={metadata} />);
  expect(confirm.hasAttribute("disabled")).toBe(false);
});

test("项目 SIP 编辑通过受控回调提交精确草稿并支持取消", () => {
  const onMetadataChange = vi.fn();
  const onConfirmMetadata = vi.fn();
  const onCancelMetadata = vi.fn();
  renderPanel({
    metadataDirty: true,
    onMetadataChange,
    onConfirmMetadata,
    onCancelMetadata,
  });

  fireEvent.click(screen.getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  fireEvent.change(screen.getByRole("textbox", { name: "产品名称" }), {
    target: { value: "新上座" },
  });
  expect(onMetadataChange).toHaveBeenCalledWith({
    ...metadata,
    material_name: "新上座",
  });

  fireEvent.click(screen.getByRole("button", {
    name: "保存项目 SIP 信息",
  }));
  fireEvent.click(screen.getByRole("button", {
    name: "取消项目 SIP 信息修改",
  }));
  expect(onConfirmMetadata).toHaveBeenCalledTimes(1);
  expect(onCancelMetadata).toHaveBeenCalledTimes(1);
});

test("图纸识别字段在编辑器中明确标记为已自动采纳", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      persistedMetadata={{}}
      metadataConfirmed={false}
      missingMetadataFields={["物料编码", "版本号", "材质"]}
      metadataSuggestions={[
        {
          field: "material_name",
          value: "上座",
          observation_id: "material-name-value",
          label_observation_id: "material-name-label",
          page_index: 0,
          bbox_pdf: [1, 2, 3, 4],
          rule_version: "welli-title-metadata/1",
          evidence_codes: ["native_line"],
        },
        {
          field: "drawing_number",
          value: "JS26032501",
          observation_id: "drawing-number-value",
          label_observation_id: "drawing-number-label",
          page_index: 0,
          bbox_pdf: [1, 2, 3, 4],
          rule_version: "welli-title-metadata/1",
          evidence_codes: ["native_line"],
        },
      ]}
    />,
  );

  expect(screen.getAllByText("图纸识别，已自动采纳")).toHaveLength(2);
  expect((
    screen.getByRole("textbox", { name: "产品名称" }) as HTMLInputElement
  ).value).toBe("上座");
  expect((
    screen.getByRole("textbox", { name: "图号" }) as HTMLInputElement
  ).value).toBe("JS26032501");
});

test("技术要求变更时优先重新生成而不保留逐项 SIP 编辑 owner", () => {
  const onSelectNextException = vi.fn();
  const onCommand = vi.fn();
  render(
    <SipInformationPanel
      {...panelProps()}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: false,
        sip_mapping_exceptions: [
          "composite_method_required",
          "sip_regeneration_required",
        ],
      })}
      pendingItemCount={0}
      readyItemCount={112}
      exceptionItemCount={3}
      regenerationRequired
      onSelectNextException={onSelectNextException}
      onCommand={onCommand}
    />,
  );

  expect(screen.getByText("SIP 表格：已生成 112，异常 3")).not.toBeNull();
  expect(screen.getByText("复合项需要选择检验方法")).not.toBeNull();
  expect(screen.getByText("技术要求已变更，请重新生成 SIP 表格")).not.toBeNull();
  expect(screen.getByRole("textbox", {
    name: "默认检验角色",
  })).not.toBeNull();
  fireEvent.change(screen.getByRole("textbox", {
    name: "默认检验角色",
  }), { target: { value: "IPQC" } });
  fireEvent.click(screen.getByRole("button", {
    name: "生成并检查 SIP 表格",
  }));
  expect(onCommand).toHaveBeenCalledWith({
    type: "generate_sip_table",
    inspection_role: "IPQC",
  });
  expect(screen.queryByRole("group", { name: "SIP 字段" })).toBeNull();
  fireEvent.click(screen.getByRole("button", {
    name: "处理下一条异常",
  }));
  expect(onSelectNextException).toHaveBeenCalledOnce();
  expect(document.body.textContent).not.toContain("已确认 112 / 115");
});

test("混合状态下待生成行不遮蔽当前真实异常", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: false,
        sip_mapping_exceptions: ["missing_inspection_role"],
      })}
      pendingItemCount={1}
      readyItemCount={111}
      exceptionItemCount={3}
      onSelectNextException={vi.fn()}
    />,
  );

  expect(screen.getByText("SIP 表格：待生成 1")).not.toBeNull();
  expect(screen.getByText("缺少默认检验角色")).not.toBeNull();
  expect(screen.getByRole("group", { name: "SIP 字段" })).not.toBeNull();
  expect(screen.getByRole("button", {
    name: "处理下一条异常",
  })).not.toBeNull();
});

test("纯重新生成异常不展示第二套手工 SIP 表单", () => {
  const selectedSipDraftSaveRef = createRef<DraftSaveHandle>();
  render(
    <SipInformationPanel
      {...panelProps()}
      selectedSipDraftSaveRef={selectedSipDraftSaveRef}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: false,
        sip_mapping_exceptions: ["sip_regeneration_required"],
      })}
      pendingItemCount={0}
      readyItemCount={114}
      exceptionItemCount={1}
      regenerationRequired
    />,
  );

  expect(screen.getByText(
    "技术要求已变更，请重新生成 SIP 表格",
  )).not.toBeNull();
  expect(screen.getByRole("button", {
    name: "生成并检查 SIP 表格",
  })).not.toBeNull();
  expect(screen.queryByRole("group", {
    name: "SIP 字段",
  })).toBeNull();
  expect(screen.queryByRole("button", {
    name: "保存当前 SIP 字段",
  })).toBeNull();
  expect(selectedSipDraftSaveRef.current).toBeNull();
});

test("重新生成异常卸载已失效的单行 SIP 草稿 owner", () => {
  const selectedSipDraftSaveRef = createRef<DraftSaveHandle>();
  const onSelectedSipDraftChange = vi.fn();
  const onCommand = vi.fn();
  const props = panelProps({
    selectedSipDraftSaveRef,
    onSelectedSipDraftChange,
    onCommand,
    pendingItemCount: 0,
    exceptionItemCount: 1,
    selectedItem: reviewItem({
      sip_detail_fields_confirmed: false,
      sip_mapping_exceptions: ["composite_method_required"],
    }),
  });
  const { rerender } = render(<SipInformationPanel {...props} />);

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M6" }), {
    target: { value: "三针法" },
  });
  expect(onSelectedSipDraftChange).toHaveBeenLastCalledWith(true);

  rerender(
    <SipInformationPanel
      {...props}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: false,
        sip_mapping_exceptions: ["sip_regeneration_required"],
      })}
      regenerationRequired
    />,
  );

  expect(selectedSipDraftSaveRef.current).toBeNull();
  expect(onSelectedSipDraftChange).toHaveBeenLastCalledWith(false);
  expect(onCommand).not.toHaveBeenCalled();
});

test("已完成当前行与全局其他 SIP 异常明确分开", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: true,
        sip_mapping_exceptions: [],
      })}
      pendingItemCount={0}
      readyItemCount={115}
      exceptionItemCount={6}
      onSelectNextException={vi.fn()}
    />,
  );

  expect(screen.getByText("SIP 表格：已生成 115，异常 6")).not.toBeNull();
  expect(screen.getByText("当前行已完成，无需处理")).not.toBeNull();
  expect(screen.getByText("全局另有 6 条 SIP 异常待处理。")).not.toBeNull();
  expect(screen.getByRole("button", {
    name: "处理下一条异常",
  })).not.toBeNull();
  expect(screen.queryByRole("group", { name: "SIP 字段" })).toBeNull();

  fireEvent.click(screen.getByRole("button", {
    name: "可选修改当前 SIP 行",
  }));

  expect(screen.getByText(
    "以下修改为可选操作，不属于异常处理。",
  )).not.toBeNull();
  expect(screen.getByRole("group", { name: "SIP 字段" })).not.toBeNull();
  expect(screen.queryByRole("button", {
    name: "可选修改当前 SIP 行",
  })).toBeNull();
});

test("没有 SIP 异常时显示完成终态并移除重复生成动作", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      selectedItem={reviewItem({
        sip_detail_fields_confirmed: true,
        sip_mapping_exceptions: [],
      })}
      pendingItemCount={0}
      readyItemCount={115}
      exceptionItemCount={0}
      onSelectNextException={vi.fn()}
    />,
  );

  expect(screen.getByText("SIP 表格：已生成 115，异常 0")).not.toBeNull();
  expect(screen.queryByRole("button", {
    name: "处理下一条异常",
  })).toBeNull();
  expect(screen.queryByRole("button", {
    name: "生成并检查 SIP 表格",
  })).toBeNull();
  expect(screen.queryByRole("textbox", {
    name: "默认检验角色",
  })).toBeNull();
  expect(screen.getByText("SIP 表格已完成")).not.toBeNull();
  expect(screen.getByText(
    "正式文件将在审核和冻结完成后从左侧统一生成。",
  )).not.toBeNull();
  expect(screen.getByText("当前行已完成，无需处理")).not.toBeNull();
  expect(screen.queryByText(/全局另有/)).toBeNull();
  expect(screen.queryByRole("group", { name: "SIP 字段" })).toBeNull();
  fireEvent.click(screen.getByRole("button", {
    name: "可选修改当前 SIP 行",
  }));
  expect(screen.getByRole("group", { name: "SIP 字段" })).not.toBeNull();
});

test("尚未生成的检验项与真实异常分开计数", () => {
  renderPanel({
    pendingItemCount: 122,
    readyItemCount: 0,
    exceptionItemCount: 0,
  });

  expect(screen.getByText("SIP 表格：待生成 122")).not.toBeNull();
  expect(screen.queryByText(/异常 122/)).toBeNull();
  expect(screen.queryByRole("button", {
    name: "处理下一条异常",
  })).toBeNull();
  expect(screen.queryByRole("group", { name: "SIP 字段" })).toBeNull();
  expect(screen.getByRole("textbox", {
    name: "默认检验角色",
  })).not.toBeNull();
});

test("没有有效检验项时保留首次生成入口", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      readyItemCount={0}
      exceptionItemCount={0}
    />,
  );

  expect(screen.getByRole("textbox", {
    name: "默认检验角色",
  })).not.toBeNull();
  expect(screen.getByRole("button", {
    name: "生成并检查 SIP 表格",
  })).not.toBeNull();
  expect(screen.queryByText("SIP 表格已完成")).toBeNull();
});

test("标题栏冲突并列显示且采用识别值只修改本地草稿", () => {
  const onMetadataChange = vi.fn();
  const onCommand = vi.fn();
  render(
    <SipInformationPanel
      {...panelProps()}
      persistedMetadata={metadata}
      metadataSuggestions={[{
        field: "material_name",
        value: "横行滑板",
        observation_id: "material-name-value",
        label_observation_id: "material-name-label",
        page_index: 0,
        bbox_pdf: [1, 2, 3, 4],
        rule_version: "welli-title-metadata/1",
        evidence_codes: ["native_line"],
      }]}
      onMetadataChange={onMetadataChange}
      onCommand={onCommand}
    />,
  );

  fireEvent.click(screen.getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  expect(screen.getByText("当前值：上座")).not.toBeNull();
  expect(screen.getByText("图纸识别值：横行滑板")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", {
    name: "采用识别值：产品名称",
  }));

  expect(onMetadataChange).toHaveBeenCalledWith({
    ...metadata,
    material_name: "横行滑板",
  });
  expect(onCommand).not.toHaveBeenCalled();
});

test("disabled 状态由项目 SIP fieldset 统一承载", () => {
  renderPanel({ disabled: true, metadataDirty: true });

  fireEvent.click(screen.getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  const fieldset = screen.getByRole("group", {
    name: "编辑项目 SIP 信息",
  }) as HTMLFieldSetElement;
  expect(fieldset.disabled).toBe(true);
});

test("没有当前检验项时显示精确 SIP 空状态", () => {
  renderPanel({ selectedItem: undefined });

  const region = screen.getByRole("region", { name: "当前检验项" });
  expect(region.textContent).toContain(
    "请选择一个有效检验项以填写 SIP 信息。",
  );
  expect(within(region).queryByRole("group", {
    name: "SIP 字段",
  })).toBeNull();
});

test("非 active 检验项显示精确 SIP 空状态", () => {
  renderPanel({ selectedItem: reviewItem({ active: false }) });

  const region = screen.getByRole("region", { name: "当前检验项" });
  expect(region.textContent).toContain(
    "请选择一个有效检验项以填写 SIP 信息。",
  );
  expect(within(region).queryByRole("group", {
    name: "SIP 字段",
  })).toBeNull();
});

test("项目和当前检验项是互不嵌套的具名可访问区域", () => {
  renderPanel();

  const sipRegion = screen.getByRole("region", { name: "SIP 信息" });
  expect(within(sipRegion).getByRole("region", {
    name: "项目基本信息",
  })).toBeTruthy();
  const currentRegion = screen.getByRole("region", {
    name: "当前检验项",
  });
  expect(sipRegion.contains(currentRegion)).toBe(false);
});

test("向当前检验项转发显式 draft save handle", async () => {
  const selectedSipDraftSaveRef = createRef<DraftSaveHandle>();
  const onCommand = vi.fn().mockResolvedValue(true);
  renderPanel({
    onCommand,
    selectedSipDraftSaveRef,
    pendingItemCount: 0,
    exceptionItemCount: 1,
    selectedItem: reviewItem({
      sip_detail_fields_confirmed: false,
      sip_mapping_exceptions: ["composite_method_required"],
    }),
  });

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M6" }), {
    target: { value: "三针法" },
  });
  await act(async () => {
    expect(
      await selectedSipDraftSaveRef.current!.saveDrafts(),
    ).toBe(true);
  });

  expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({
    type: "set_sip_detail_fields",
    item_id: "item-1",
    inspection_method: "三针法",
  }));
});
