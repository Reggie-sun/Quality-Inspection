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
    metadataDirty: false,
    disabled: false,
    selectedItem: reviewItem(),
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

test("统一 SIP 区域同时呈现项目信息和当前检验项", () => {
  renderPanel();

  const region = screen.getByRole("region", { name: "SIP 信息" });
  expect(within(region).getByRole("heading", {
    level: 2,
    name: "SIP 信息",
  })).toBeTruthy();
  expect(within(region).getByRole("heading", {
    level: 3,
    name: "项目基本信息",
  })).toBeTruthy();
  expect(within(region).getByRole("heading", {
    level: 3,
    name: "当前检验项",
  })).toBeTruthy();
  expect(within(region).getByRole("group", {
    name: "SIP 确认字段",
  })).toBeTruthy();
  expect(region.textContent).toContain("产品名称上座");
  expect(region.textContent).toContain("图号JS26032501");
  expect(region.textContent).toContain("单位—");
});

test("切到待判定来源时保留项目区和当前检验项草稿", () => {
  const props = panelProps();
  const { rerender } = render(<SipInformationPanel {...props} />);

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M6" }), {
    target: { value: "三针法复核" },
  });
  rerender(<SipInformationPanel {...props} selectedSourceActive />);

  const region = screen.getByRole("region", { name: "SIP 信息" });
  expect(within(region).getByRole("heading", {
    level: 3,
    name: "项目基本信息",
  })).toBeTruthy();
  expect(region.textContent).toContain("产品名称上座");
  expect(region.textContent).toContain("当前选择的是待判定来源。");
  expect(within(region).queryByRole("group", {
    name: "SIP 确认字段",
  })).toBeNull();

  rerender(<SipInformationPanel {...props} selectedSourceActive={false} />);
  expect(
    (screen.getByRole("textbox", {
      name: "检验方法：M6",
    }) as HTMLInputElement).value,
  ).toBe("三针法复核");
});

test("项目 SIP 信息不完整时禁用确认，补全后启用", () => {
  const incompleteMetadata = { ...metadata, material_code: "" };
  const props = panelProps({ metadata: incompleteMetadata });
  const { rerender } = render(<SipInformationPanel {...props} />);

  fireEvent.click(screen.getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  const confirm = screen.getByRole("button", {
    name: "确认项目 SIP 信息",
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
    name: "确认项目 SIP 信息",
  }));
  fireEvent.click(screen.getByRole("button", {
    name: "取消项目 SIP 信息修改",
  }));
  expect(onConfirmMetadata).toHaveBeenCalledTimes(1);
  expect(onCancelMetadata).toHaveBeenCalledTimes(1);
});

test("图纸识别字段在编辑器中明确标记为待确认建议", () => {
  render(
    <SipInformationPanel
      {...panelProps()}
      suggestedMetadataFields={["material_name", "drawing_number"]}
    />,
  );

  fireEvent.click(screen.getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  expect(screen.getAllByText("图纸识别，待确认")).toHaveLength(2);
  expect((
    screen.getByRole("textbox", { name: "产品名称" }) as HTMLInputElement
  ).value).toBe("上座");
  expect((
    screen.getByRole("textbox", { name: "图号" }) as HTMLInputElement
  ).value).toBe("JS26032501");
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

  const region = screen.getByRole("region", { name: "SIP 信息" });
  expect(region.textContent).toContain(
    "请选择一个有效检验项以填写 SIP 信息。",
  );
  expect(within(region).queryByRole("group", {
    name: "SIP 确认字段",
  })).toBeNull();
});

test("非 active 检验项显示精确 SIP 空状态", () => {
  renderPanel({ selectedItem: reviewItem({ active: false }) });

  const region = screen.getByRole("region", { name: "SIP 信息" });
  expect(region.textContent).toContain(
    "请选择一个有效检验项以填写 SIP 信息。",
  );
  expect(within(region).queryByRole("group", {
    name: "SIP 确认字段",
  })).toBeNull();
});

test("项目和当前检验项子区是具名可访问区域", () => {
  renderPanel();

  const region = screen.getByRole("region", { name: "SIP 信息" });
  expect(within(region).getByRole("region", {
    name: "项目基本信息",
  })).toBeTruthy();
  expect(within(region).getByRole("region", {
    name: "当前检验项",
  })).toBeTruthy();
});

test("向当前检验项转发显式 draft save handle", async () => {
  const selectedSipDraftSaveRef = createRef<DraftSaveHandle>();
  const onCommand = vi.fn().mockResolvedValue(true);
  renderPanel({
    onCommand,
    selectedSipDraftSaveRef,
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
