import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ReviewItem } from "../../api/types";
import { SelectedSipDetailFields } from "./SelectedSipDetailFields";


afterEach(cleanup);

function reviewItem(
  itemId: string,
  rawText: string,
  overrides: Partial<ReviewItem> = {},
): ReviewItem {
  return {
    item_id: itemId,
    raw_text: rawText,
    item_type: "thread",
    inspection_item: "螺纹检验",
    inspection_standard: "GB/T 197",
    inspection_method: "螺纹规",
    key_dimension: "是",
    inspection_role: "检验员",
    source_page: 1,
    remarks: "原始备注",
    active: true,
    ...overrides,
  };
}

test("编辑备注提交既有 SIP command，成功后报告 dirty false", async () => {
  const onCommand = vi.fn();
  const onDraftChange = vi.fn();
  render(
    <SelectedSipDetailFields
      item={reviewItem("remarks-item", "M6")}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "备注（可选）：M6" }), {
    target: { value: "首件需复核" },
  });
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", {
    name: "确认当前检验项 SIP",
  }));

  await waitFor(() => {
    expect(onCommand).toHaveBeenCalledWith({
      type: "set_sip_detail_fields",
      item_id: "remarks-item",
      inspection_item: "螺纹检验",
      inspection_standard: "GB/T 197",
      inspection_method: "螺纹规",
      key_dimension: "是",
      inspection_role: "检验员",
      source_page: 1,
      remarks: "首件需复核",
    });
    expect(onDraftChange).toHaveBeenLastCalledWith(false);
  });
});

test("保存失败后切换检验项再返回仍保留方法草稿和 dirty true", async () => {
  const onCommand = vi.fn().mockResolvedValue(false);
  const onDraftChange = vi.fn();
  const firstItem = reviewItem("sip-retry", "M10");
  const secondItem = reviewItem("other-item", "M12", {
    inspection_method: "通止规",
    source_page: 2,
  });
  const { rerender } = render(
    <SelectedSipDetailFields
      item={firstItem}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M10" }), {
    target: { value: "三针法复核" },
  });
  fireEvent.click(screen.getByRole("button", {
    name: "确认当前检验项 SIP",
  }));

  await waitFor(() => expect(onCommand).toHaveBeenCalledWith({
    type: "set_sip_detail_fields",
    item_id: "sip-retry",
    inspection_item: "螺纹检验",
    inspection_standard: "GB/T 197",
    inspection_method: "三针法复核",
    key_dimension: "是",
    inspection_role: "检验员",
    source_page: 1,
    remarks: "原始备注",
  }));

  rerender(
    <SelectedSipDetailFields
      item={secondItem}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );
  rerender(
    <SelectedSipDetailFields
      item={firstItem}
      onCommand={onCommand}
      onDraftChange={onDraftChange}
    />,
  );

  expect(
    (screen.getByRole("textbox", {
      name: "检验方法：M10",
    }) as HTMLInputElement).value,
  ).toBe("三针法复核");
  expect(onDraftChange).toHaveBeenLastCalledWith(true);
});

test("取消修改恢复当前后端备注基线且不发送 command", () => {
  const onCommand = vi.fn();
  render(
    <SelectedSipDetailFields
      item={reviewItem("remarks-cancel", "Ra 3.2", {
        item_type: "general_requirement",
        inspection_item: "表面粗糙度",
        inspection_standard: "图纸要求",
        inspection_method: "粗糙度仪",
        key_dimension: "否",
        remarks: "保留原文",
      })}
      onCommand={onCommand}
    />,
  );

  const remarks = screen.getByRole("textbox", {
    name: "备注（可选）：Ra 3.2",
  }) as HTMLTextAreaElement;
  fireEvent.change(remarks, { target: { value: "临时修改" } });
  fireEvent.click(screen.getByRole("button", {
    name: "取消当前检验项 SIP 修改",
  }));

  expect(remarks.value).toBe("保留原文");
  expect(onCommand).not.toHaveBeenCalled();
});

test("待判定来源式空 item 状态不提交 SIP command", () => {
  const onCommand = vi.fn();
  const item = reviewItem("source-switch-item", "M16");
  const { rerender } = render(
    <SelectedSipDetailFields
      item={item}
      onCommand={onCommand}
    />,
  );

  fireEvent.change(screen.getByRole("textbox", { name: "检验方法：M16" }), {
    target: { value: "三针法" },
  });
  rerender(
    <SelectedSipDetailFields
      item={undefined}
      balloon={undefined}
      onCommand={onCommand}
    />,
  );
  expect(screen.queryByRole("group", { name: "SIP 确认字段" })).toBeNull();
  expect(onCommand).not.toHaveBeenCalled();

  rerender(
    <SelectedSipDetailFields
      item={item}
      onCommand={onCommand}
    />,
  );
  expect(
    (screen.getByRole("textbox", {
      name: "检验方法：M16",
    }) as HTMLInputElement).value,
  ).toBe("三针法");
});
