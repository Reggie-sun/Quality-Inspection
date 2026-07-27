import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  MergeInspectionItemsPreview,
  suggestMergedRawText,
} from "./MergeInspectionItemsPreview";


afterEach(cleanup);

const items = [
  {
    item_id: "item-1",
    raw_text: "48",
    item_type: "linear_dimension" as const,
    active: true,
  },
  {
    item_id: "item-2",
    raw_text: "±0.1",
    item_type: "general_requirement" as const,
    active: true,
  },
];

function renderPreview(
  overrides: Partial<Parameters<typeof MergeInspectionItemsPreview>[0]> = {},
) {
  const props = {
    items,
    draftRawText: "48 ±0.1",
    submitting: false,
    onDraftRawTextChange: vi.fn(),
    onBack: vi.fn(),
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };

  render(<MergeInspectionItemsPreview {...props} />);
  return props;
}

describe("suggestMergedRawText", () => {
  test("trims and removes exact duplicates in first-seen order", () => {
    expect(suggestMergedRawText([" 48 ", "48"])).toBe("48");
  });

  test("joins distinct source values with one space", () => {
    expect(suggestMergedRawText(["⌀10", " ±0.1 "])).toBe("⌀10 ±0.1");
  });

  test("drops blank values without changing later order", () => {
    expect(suggestMergedRawText(["A", "", "A", "B"])).toBe("A B");
  });
});

test("shows every source value and type label for context", () => {
  renderPreview();

  expect(screen.getByText("48")).not.toBeNull();
  expect(screen.getByText("±0.1")).not.toBeNull();
  expect(screen.getByText("线性尺寸")).not.toBeNull();
  expect(screen.getByText("通用要求")).not.toBeNull();
  expect(screen.getByText("合并不是数值相加")).not.toBeNull();
});

test("reports edits to the parent-owned merged raw text draft", () => {
  const onDraftRawTextChange = vi.fn();
  renderPreview({ onDraftRawTextChange });

  const draft = screen.getByRole("textbox", { name: "合并后的原始标注" });
  expect((draft as HTMLTextAreaElement).value).toBe("48 ±0.1");

  fireEvent.change(draft, { target: { value: "48 ±0.05" } });

  expect(onDraftRawTextChange).toHaveBeenCalledOnce();
  expect(onDraftRawTextChange).toHaveBeenCalledWith("48 ±0.05");
});

test("returns or cancels without confirming", () => {
  const props = renderPreview();

  fireEvent.click(screen.getByRole("button", { name: "返回修改" }));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));

  expect(props.onBack).toHaveBeenCalledOnce();
  expect(props.onCancel).toHaveBeenCalledOnce();
  expect(props.onConfirm).not.toHaveBeenCalled();
});

test("confirms the current two-item merge only once per click", () => {
  const props = renderPreview();

  fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));

  expect(props.onConfirm).toHaveBeenCalledOnce();
});

test("disables every navigation and confirmation action while submitting", () => {
  const { rerender } = render(
    <MergeInspectionItemsPreview
      items={items}
      draftRawText="48 ±0.1"
      submitting
      onDraftRawTextChange={vi.fn()}
      onBack={vi.fn()}
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );

  const submittingConfirm = screen.getByRole(
    "button",
    { name: "确认合并 2 项" },
  ) as HTMLButtonElement;
  const submittingBack = screen.getByRole(
    "button",
    { name: "返回修改" },
  ) as HTMLButtonElement;
  const submittingCancel = screen.getByRole(
    "button",
    { name: "取消" },
  ) as HTMLButtonElement;
  expect(submittingBack.disabled).toBe(true);
  expect(submittingCancel.disabled).toBe(true);
  expect(submittingConfirm.disabled).toBe(true);

  rerender(
    <MergeInspectionItemsPreview
      items={items}
      draftRawText="   "
      submitting={false}
      onDraftRawTextChange={vi.fn()}
      onBack={vi.fn()}
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );

  const blankConfirm = screen.getByRole(
    "button",
    { name: "确认合并 2 项" },
  ) as HTMLButtonElement;
  expect(blankConfirm.disabled).toBe(true);
});

test("moves focus to the preview heading on mount", () => {
  renderPreview();

  expect(document.activeElement).toBe(
    screen.getByRole("heading", { name: "合并预览" }),
  );
});
