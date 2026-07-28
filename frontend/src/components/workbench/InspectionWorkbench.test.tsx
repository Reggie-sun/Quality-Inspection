import { useEffect, useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { PostJson, ReviewCommand, ReviewItem } from "../../api/types";
import { InspectionWorkbench } from "./InspectionWorkbench";


afterEach(cleanup);

function openAuxiliaryPanel(): void {
  fireEvent.click(screen.getByRole("button", {
    name: "展开 SIP 与导出信息",
  }));
}

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const mergeSourceItems = [
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

function MergeRefreshHarness({
  initialItems,
  onSave,
  refreshedItems,
  saveCompletion,
}: {
  initialItems: ReviewItem[];
  onSave: (command: ReviewCommand) => Promise<void> | void;
  refreshedItems: ReviewItem[];
  saveCompletion?: Promise<void>;
}) {
  const [items, setItems] = useState(initialItems);
  return (
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={items}
      onSave={async (command) => {
        await onSave(command);
        await Promise.resolve();
        setItems(refreshedItems);
        if (saveCompletion !== undefined) await saveCompletion;
      }}
    />
  );
}

function DelayedMergeRefreshHarness({
  initialItems,
  onSave,
  refreshedItems,
  refreshCompletion,
}: {
  initialItems: ReviewItem[];
  onSave: (command: ReviewCommand) => Promise<void>;
  refreshedItems: ReviewItem[];
  refreshCompletion: Promise<void>;
}) {
  const [items, setItems] = useState(initialItems);
  useEffect(() => {
    let active = true;
    void refreshCompletion.then(() => {
      if (active) setItems(refreshedItems);
    });
    return () => {
      active = false;
    };
  }, [refreshCompletion, refreshedItems]);
  return (
    <InspectionWorkbench
      pdfDocument={null}
      candidates={[]}
      sources={[]}
      balloons={[]}
      items={items}
      onSave={onSave}
    />
  );
}

function openMergePreview(rawText = "  ⌀10 ±0.1  "): void {
  fireEvent.click(screen.getByRole("button", { name: "合并重复项" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /⌀10/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: /±0\.1/ }));
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  fireEvent.change(screen.getByRole("textbox", {
    name: "合并后的原始标注",
  }), { target: { value: rawText } });
}

describe("InspectionWorkbench", () => {
  test("本地草稿立即显示未保存且只在修改保存时提交", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "修改检验项：M6" }));
    fireEvent.change(screen.getByRole("textbox", { name: "原始标注：M6" }), {
      target: { value: "M8" },
    });

    expect(saveStatus.textContent).toBe("有未保存修改");
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", {
      name: "修改保存检验项：M6",
    }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "edit",
      item_id: "i1",
      fields: {
        raw_text: "M8",
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

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    const rawText = screen.getByRole("textbox", {
      name: "原始标注：10",
    }) as HTMLInputElement;
    fireEvent.change(rawText, { target: { value: "10.0" } });

    fireEvent.click(screen.getByRole("row", { name: /20/ }));

    expect(screen.queryByRole("region", { name: "所选检验项" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "原始标注：20" })).toBeNull();
    expect(rawText.value).toBe("10.0");
    expect(within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status").textContent).toBe("请先修改保存当前检验项");
  });

  test("未保存的 ReviewPanel 编辑阻止进入合并且保留当前草稿", () => {
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={mergeSourceItems}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：⌀10",
    }));
    const rawText = screen.getByRole("textbox", {
      name: "原始标注：⌀10",
    }) as HTMLInputElement;
    fireEvent.change(rawText, { target: { value: "⌀10 H7" } });
    fireEvent.click(screen.getByRole("button", { name: "合并重复项" }));

    expect(screen.queryAllByRole("checkbox", {
      name: /选择检验项/,
    })).toHaveLength(0);
    expect(within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status").textContent).toBe("请先修改保存当前检验项");
    expect(rawText.value).toBe("⌀10 H7");
  });

  test("合并确认期间重复点击只通过唯一提交路径保存一次", async () => {
    const deferred = createDeferred<void>();
    const onSave = vi.fn(() => deferred.promise);
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        items={mergeSourceItems}
        onSave={onSave}
      />,
    );

    openMergePreview();
    const confirm = screen.getByRole("button", { name: "确认合并 2 项" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave).toHaveBeenCalledWith({
      type: "merge",
      item_ids: ["item-1", "item-2"],
      raw_text: "⌀10 ±0.1",
    });

    deferred.resolve();
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
    });
  });

  test("合并刷新后只选择唯一新增的 active 检验项", async () => {
    const refreshedItems = [
      { ...mergeSourceItems[0], active: false },
      { ...mergeSourceItems[1], active: false },
      {
        item_id: "merged-1",
        item_type: "linear_dimension" as const,
        raw_text: "⌀10 ±0.1",
        active: true,
      },
    ];
    const onSave = vi.fn();
    render(
      <MergeRefreshHarness
        initialItems={mergeSourceItems}
        refreshedItems={refreshedItems}
        onSave={onSave}
      />,
    );

    openMergePreview();
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledOnce();
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("merged-1");
      expect(screen.getByRole("heading", {
        name: "检验项 — · 线性尺寸",
      })).not.toBeNull();
      expect(screen.getByRole("textbox", {
        name: "原始标注：⌀10 ±0.1",
      })).not.toBeNull();
    });
  });

  test("合并成功但没有新增 active 检验项时清除失效选择且不猜测", async () => {
    const refreshedItems = mergeSourceItems.map((item) => ({
      ...item,
      active: false,
    }));
    render(
      <MergeRefreshHarness
        initialItems={mergeSourceItems}
        refreshedItems={refreshedItems}
        onSave={vi.fn()}
      />,
    );

    openMergePreview();
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("__no_selected_review_item__");
      expect(screen.queryByRole("article", { name: /检验项/ })).toBeNull();
      expect(screen.queryAllByRole("checkbox", {
        name: /选择检验项/,
      })).toHaveLength(0);
    });
  });

  test("合并成功但有两个新增 active 检验项时保留仍合法的选择", async () => {
    const initialItems = [
      {
        item_id: "item-1",
        item_type: "thread" as const,
        raw_text: "M6",
        active: true,
      },
      {
        item_id: "item-2",
        item_type: "linear_dimension" as const,
        raw_text: "⌀10",
        active: true,
      },
      {
        item_id: "item-3",
        item_type: "general_requirement" as const,
        raw_text: "±0.1",
        active: true,
      },
    ];
    const refreshedItems = [
      initialItems[0],
      { ...initialItems[1], active: false },
      { ...initialItems[2], active: false },
      {
        item_id: "merged-a",
        item_type: "linear_dimension" as const,
        raw_text: "合并候选 A",
        active: true,
      },
      {
        item_id: "merged-b",
        item_type: "linear_dimension" as const,
        raw_text: "合并候选 B",
        active: true,
      },
    ];
    render(
      <MergeRefreshHarness
        initialItems={initialItems}
        refreshedItems={refreshedItems}
        onSave={vi.fn()}
      />,
    );

    openMergePreview();
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("item-1");
      expect(screen.getByRole("heading", {
        name: "检验项 — · 螺纹",
      })).not.toBeNull();
      expect(screen.getByRole("textbox", {
        name: "原始标注：M6",
      })).not.toBeNull();
      expect(screen.queryByRole("textbox", {
        name: "原始标注：合并候选 A",
      })).toBeNull();
      expect(screen.queryByRole("textbox", {
        name: "原始标注：合并候选 B",
      })).toBeNull();
    });
  });

  test("合并刷新先 commit、保存后 resolve 时仍只选择唯一新增项", async () => {
    const deferred = createDeferred<void>();
    const refreshedItems = [
      { ...mergeSourceItems[0], active: false },
      { ...mergeSourceItems[1], active: false },
      {
        item_id: "merged-before-resolve",
        item_type: "linear_dimension" as const,
        raw_text: "先刷新后完成",
        active: true,
      },
    ];
    render(
      <MergeRefreshHarness
        initialItems={mergeSourceItems}
        refreshedItems={refreshedItems}
        onSave={vi.fn()}
        saveCompletion={deferred.promise}
      />,
    );

    openMergePreview();
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));
    await waitFor(() => {
      expect(screen.getByTestId("summary-active-count").textContent).toBe("1");
    });
    deferred.resolve();

    await waitFor(() => {
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("merged-before-resolve");
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
    });
  });

  test("合并成功后在 refresh commit 前阻止其他审核命令和第二次合并", async () => {
    const refresh = createDeferred<void>();
    const refreshedItems = [
      { ...mergeSourceItems[0], active: false },
      { ...mergeSourceItems[1], active: false },
      {
        item_id: "merged-after-delay",
        item_type: "linear_dimension" as const,
        raw_text: "延迟刷新后的合并项",
        active: true,
      },
    ];
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <DelayedMergeRefreshHarness
        initialItems={mergeSourceItems}
        refreshedItems={refreshedItems}
        refreshCompletion={refresh.promise}
        onSave={onSave}
      />,
    );

    openMergePreview();
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledOnce();
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
    });

    const beginMerge = screen.getByRole(
      "button",
      { name: "合并重复项" },
    ) as HTMLButtonElement;
    expect(beginMerge.disabled).toBe(true);
    fireEvent.click(beginMerge);
    expect(screen.queryAllByRole("checkbox", {
      name: /选择检验项/,
    })).toHaveLength(0);

    const keep = screen.getByRole(
      "button",
      { name: "保留检验项：⌀10" },
    ) as HTMLButtonElement;
    fireEvent.click(keep);
    expect(onSave).toHaveBeenCalledOnce();
    expect(keep.disabled).toBe(true);

    refresh.resolve();
    await waitFor(() => {
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("merged-after-delay");
      expect(beginMerge.disabled).toBe(false);
      expect((screen.getByRole(
        "button",
        { name: "保留检验项：延迟刷新后的合并项" },
      ) as HTMLButtonElement).disabled).toBe(false);
    });
  });

  test("合并保存失败保留预览选择和草稿，重试相同命令后可成功", async () => {
    const refreshedItems = [
      { ...mergeSourceItems[0], active: false },
      { ...mergeSourceItems[1], active: false },
      {
        item_id: "merged-after-retry",
        item_type: "linear_dimension" as const,
        raw_text: "保留的合并草稿",
        active: true,
      },
    ];
    const onSave = vi.fn()
      .mockRejectedValueOnce(new Error("save failed"))
      .mockResolvedValueOnce(undefined);
    render(
      <MergeRefreshHarness
        initialItems={mergeSourceItems}
        refreshedItems={refreshedItems}
        onSave={onSave}
      />,
    );

    openMergePreview("  保留的合并草稿  ");
    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));

    await waitFor(() => {
      expect(within(
        screen.getByRole("region", { name: "项目摘要" }),
      ).getByRole("status").textContent).toBe("保存失败");
      expect(screen.getByRole("alert").textContent).toBe("合并失败，请重试");
    });
    expect((screen.getByRole("textbox", {
      name: "合并后的原始标注",
    }) as HTMLTextAreaElement).value).toBe("  保留的合并草稿  ");
    expect(screen.getByText("⌀10")).not.toBeNull();
    expect(screen.getByText("±0.1")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "确认合并 2 项" }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("heading", { name: "合并预览" })).toBeNull();
      expect(within(
        screen.getByRole("region", { name: "项目摘要" }),
      ).getByRole("status").textContent).toBe("已保存");
      expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id"))
        .toBe("merged-after-retry");
    });
    expect(onSave.mock.calls[0]?.[0]).toEqual({
      type: "merge",
      item_ids: ["item-1", "item-2"],
      raw_text: "保留的合并草稿",
    });
    expect(onSave.mock.calls[1]?.[0]).toEqual(onSave.mock.calls[0]?.[0]);
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

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    const rawText = screen.getByRole("textbox", {
      name: "原始标注：10",
    }) as HTMLInputElement;
    fireEvent.change(rawText, { target: { value: "10.0" } });
    fireEvent.click(screen.getByRole("row", { name: /20/ }));
    fireEvent.click(screen.getByRole("button", {
      name: "修改保存检验项：10",
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
          raw_text: "10.0",
        },
      });
      expect(saveStatus.textContent).toBe("保存失败");
    });
    expect(rawText.value).toBe("10.0");
    expect(rawText.hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", {
      name: "修改保存检验项：10",
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

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(screen.getByRole("textbox", {
      name: "原始标注：10",
    }), { target: { value: "10.0" } });

    const candidate = screen.getByTestId("candidate-number-candidate-20");
    fireEvent.click(candidate);
    expect(screen.getByRole("article", {
      name: "检验项 — · 线性尺寸",
    })).not.toBeNull();
    expect(candidate.getAttribute("data-selected")).toBe("false");

    fireEvent.click(screen.getByRole("button", {
      name: "修改保存检验项：10",
    }));
    const saveStatus = within(
      screen.getByRole("region", { name: "项目摘要" }),
    ).getByRole("status");
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "edit",
        item_id: "item-10",
        fields: {
          raw_text: "10.0",
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

    fireEvent.click(screen.getByRole("button", {
      name: "修改检验项：10",
    }));
    fireEvent.change(screen.getByRole("textbox", {
      name: "原始标注：10",
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
    expect(saveStatus.textContent).toBe("请先修改保存当前检验项");

    fireEvent.click(screen.getByRole("button", {
      name: "修改保存检验项：10",
    }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith({
        type: "edit",
        item_id: "item-10",
        fields: {
          raw_text: "10.0",
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

  test("visual pending sources stay distinct and require explicit owner actions", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const visualCoarseItem: ReviewItem = {
      item_id: "visual-roughness-item",
      raw_text: "Ra 3.2",
      coarse_type: "roughness",
      requires_confirmation: true,
      source_location_ids: ["visual-roughness"],
      active: true,
    };
    render(
      <InspectionWorkbench
        pdfDocument={null}
        candidates={[]}
        sources={[
          {
            id: "visual-no-detection",
            pageIndex: 0,
            bbox: [10, 20, 30, 40],
            rawText: "图形符号待确认",
            sourceType: "visual",
          },
          {
            id: "visual-revision",
            pageIndex: 1,
            bbox: [40, 50, 70, 80],
            rawText: "图形符号待确认",
            sourceType: "visual",
          },
          {
            id: "visual-roughness",
            itemIds: ["visual-roughness-item"],
            pageIndex: 0,
            bbox: [80, 90, 120, 110],
            rawText: "图形符号待确认",
            sourceType: "visual",
          },
        ]}
        balloons={[]}
        items={[visualCoarseItem]}
        workingCopy={{
          id: "visual-working",
          project_id: "visual-project",
          raw_result_id: "visual-result",
          version: 1,
          items: [visualCoarseItem],
          coverage: {
            blocking_count: 0,
            review_required_count: 2,
            entries: [
              {
                observation_id: "visual-no-detection",
                source_location_id: "visual-no-detection",
                candidate_id: null,
                disposition: "ambiguous",
                coordinates: [10, 20, 30, 40],
                requires_confirmation: true,
                symbol_kinds: [],
                rejection_code: "visual_no_detection",
              },
              {
                observation_id: "visual-revision",
                source_location_id: "visual-revision",
                candidate_id: null,
                disposition: "non_inspection",
                coordinates: [40, 50, 70, 80],
                requires_confirmation: true,
                symbol_kinds: ["revision_marker"],
              },
            ],
          },
          numbering_stale: false,
          items_frozen_at: null,
          items_frozen_by: null,
          items_frozen_version: null,
        }}
        onSave={onSave}
      />,
    );

    expect(screen.getByRole("row", { name: /图形符号待确认/ })).not.toBeNull();
    expect(screen.getByRole("row", {
      name: /修订标记（非检验）待确认/,
    })).not.toBeNull();
    const coarseRow = screen.getByRole("row", { name: /Ra 3.2/ });
    expect(coarseRow.textContent).toContain("粗糙度 · 图形转写");
    expect(coarseRow.textContent).toContain("需确认");
    expect(onSave).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain("visual-symbol-review/1");
    expect(document.body.textContent).not.toContain("provider_response");

    fireEvent.click(screen.getByRole("row", { name: /图形符号待确认/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "检验类型" }), {
      target: { value: "general_requirement" },
    });
    expect(screen.getByRole("button", { name: "添加为检验项" })
      .hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "原始标注" }), {
      target: { value: "人工确认的图形检验要求" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加为检验项" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      type: "promote_source",
      observation_id: "visual-no-detection",
      raw_text: "人工确认的图形检验要求",
      item_type: "general_requirement",
      scope: "local_feature",
      balloon_required: true,
      page_index: 0,
    }));

    fireEvent.click(screen.getByRole("row", {
      name: /修订标记（非检验）待确认/,
    }));
    expect(onSave).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", {
      name: "忽略，不作为检验项",
    }));
    await waitFor(() => expect(onSave).toHaveBeenLastCalledWith({
      type: "ignore_source",
      observation_id: "visual-revision",
    }));
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
