import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { PdfDocumentLike } from "../../api/types";
import { PdfWorkspace } from "./PdfWorkspace";


function documentFixture(): PdfDocumentLike {
  return {
    numPages: 2,
    getPage: vi.fn(async (pageNumber: number) => ({
      getViewport: ({ scale }: { scale: number }) => ({
        width: (pageNumber === 1 ? 100 : 120) * scale,
        height: 200 * scale,
      }),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    })),
  };
}

function rotatedDocumentFixture(): PdfDocumentLike {
  return {
    numPages: 1,
    getPage: vi.fn(async () => ({
      getViewport: ({ scale }: { scale: number }) => ({
        width: 200 * scale,
        height: 100 * scale,
      }),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    })),
  };
}


describe("PdfWorkspace", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as CanvasRenderingContext2D,
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  test("P0-UI-001 switches pages and preserves the current selection", async () => {
    const pdfDocument = documentFixture();
    render(
      <PdfWorkspace
        pdfDocument={pdfDocument}
        candidates={[{ id: "c1", pageIndex: 0, bbox: [10, 20, 30, 40] }]}
        sources={[]}
        balloons={[]}
      />,
    );

    fireEvent.click(await screen.findByTestId("candidate-c1"));
    expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id")).toBe(
      "c1",
    );

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => {
      expect(pdfDocument.getPage).toHaveBeenCalledWith(2);
    });
    expect(screen.getByTestId("pdf-workspace").getAttribute("data-selected-id")).toBe(
      "c1",
    );
    expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 2");
  });

  test("分页与缩放状态复用工具栏垂直居中样式", () => {
    render(
      <PdfWorkspace
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );

    expect(screen.getByTestId("page-indicator").classList.contains("pdf-control-status"))
      .toBe(true);
    expect(screen.getByLabelText("缩放比例").classList.contains("pdf-control-status"))
      .toBe(true);
  });

  test("P0-UI-002 zooms overlays with the PDF viewport", async () => {
    const bbox: [number, number, number, number] = [10, 20, 30, 40];
    render(
      <PdfWorkspace
        pdfDocument={rotatedDocumentFixture()}
        pageTransforms={[
          {
            pageIndex: 0,
            pdfToRenderMatrix: [0, 2, -2, 0, 400, 0],
          },
        ]}
        candidates={[{ id: "c1", pageIndex: 0, bbox }]}
        sources={[]}
        balloons={[{ id: "b1", pageIndex: 0, center: [80, 90], number: 1 }]}
      />,
    );
    const overlay = await screen.findByLabelText("工程图纸标注层");
    expect(overlay.getAttribute("data-scale")).toBe("1");
    expect(screen.getByTestId("candidate-c1").getAttribute("x")).toBe("160");
    expect(screen.getByTestId("candidate-c1").getAttribute("y")).toBe("10");
    expect(screen.getByTestId("candidate-c1").getAttribute("width")).toBe("20");
    expect(screen.getByTestId("candidate-c1").getAttribute("height")).toBe("20");
    const balloon = screen.getByTestId("balloon-b1").querySelector("circle");
    expect(balloon?.getAttribute("cx")).toBe("110");
    expect(balloon?.getAttribute("cy")).toBe("80");

    fireEvent.click(screen.getByRole("button", { name: "放大" }));

    await waitFor(() => {
      expect(overlay.getAttribute("data-scale")).toBe("1.25");
      expect(overlay.getAttribute("width")).toBe("250");
    });
    expect(screen.getByTestId("pdf-canvas").getAttribute("width")).toBe("250");
    expect(bbox).toEqual([10, 20, 30, 40]);
  });

  test("P0-UI-001 switches pages without leaking PDF.js cancellation rejection", async () => {
    const tasks: Array<{
      cancel: ReturnType<typeof vi.fn>;
      viewportWidth: number;
    }> = [];
    const pdfDocument: PdfDocumentLike = {
      numPages: 2,
      getPage: vi.fn(async () => ({
        getViewport: ({ scale }: { scale: number }) => ({
          width: 100 * scale,
          height: 200 * scale,
        }),
        render: vi.fn(({ viewport }: {
          canvasContext: CanvasRenderingContext2D;
          viewport: { width: number; height: number };
        }) => {
          let rejectRender!: (reason: unknown) => void;
          const promise = new Promise<unknown>((_resolve, reject) => {
            rejectRender = reject;
          });
          const cancel = vi.fn(() => {
            const error = new Error("render cancelled");
            error.name = "RenderingCancelledException";
            rejectRender(error);
          });
          tasks.push({ cancel, viewportWidth: viewport.width });
          return { promise, cancel };
        }),
      })),
    };
    render(
      <PdfWorkspace
        pdfDocument={pdfDocument}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );
    await waitFor(() => {
      expect(tasks.find((task) => task.viewportWidth === 100)).toBeDefined();
    });
    const mainPageTask = tasks.find((task) => task.viewportWidth === 100)!;

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => expect(mainPageTask.cancel).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("P0-UI-001 switches pages after surfacing a PDF render failure", async () => {
    const pdfDocument: PdfDocumentLike = {
      numPages: 2,
      getPage: vi.fn(async (pageNumber: number) => ({
        getViewport: ({ scale }: { scale: number }) => ({
          width: 100 * scale,
          height: 200 * scale,
        }),
        render: vi.fn(() => ({
          promise:
            pageNumber === 1
              ? Promise.reject(new Error("render failed"))
              : Promise.resolve(),
          cancel: vi.fn(),
        })),
      })),
    };
    render(
      <PdfWorkspace
        pdfDocument={pdfDocument}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );
    expect(await screen.findByRole("alert")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 2");
  });

  test("P0-UI-003 pans without mutating pdf coordinates", async () => {
    const bbox: [number, number, number, number] = [10, 20, 30, 40];
    const original = [...bbox];
    render(
      <PdfWorkspace
        pdfDocument={documentFixture()}
        candidates={[{ id: "c1", pageIndex: 0, bbox }]}
        sources={[]}
        balloons={[]}
      />,
    );
    await screen.findByTestId("candidate-c1");

    fireEvent.click(screen.getByRole("button", { name: "向右平移" }));

    expect(screen.getByTestId("pdf-page-layer").getAttribute("style")).toContain(
      "translate(24px, 0px)",
    );
    expect(bbox).toEqual(original);
    expect(screen.getByTestId("candidate-c1").getAttribute("x")).toBe("10");
  });

  test("来源待确认选择会跳页并高亮真实来源框", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const onSelectSource = vi.fn();
    const { rerender } = render(
      <PdfWorkspace
        pdfDocument={documentFixture()}
        candidates={[]}
        sources={[
          {
            id: "source-only",
            pageIndex: 1,
            bbox: [10, 20, 30, 40],
            rawText: "技术要求：去除毛刺",
          },
          {
            id: "source-next",
            pageIndex: 1,
            bbox: [50, 60, 70, 80],
            rawText: "125 X 2",
          },
        ]}
        balloons={[]}
        selectedSourceId="source-only"
        onSelectSource={onSelectSource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 2");
    });
    const source = await screen.findByTestId("source-source-only");
    expect(source.getAttribute("data-selected")).toBe("true");
    expect(source.getAttribute("fill")).not.toBe("transparent");
    expect(source.getAttribute("stroke")).toBe("#f59e0b");
    expect(source.getAttribute("stroke-dasharray")).toBe("none");
    expect(Number(source.getAttribute("stroke-width"))).toBeGreaterThan(1.5);
    expect(scrollIntoView).toHaveBeenCalledWith({
      block: "center",
      inline: "center",
    });
    fireEvent.click(source);
    expect(onSelectSource).toHaveBeenCalledWith("source-only");

    scrollIntoView.mockClear();
    rerender(
      <PdfWorkspace
        pdfDocument={documentFixture()}
        candidates={[]}
        sources={[
          {
            id: "source-only",
            itemIds: ["item-other"],
            pageIndex: 1,
            bbox: [10, 20, 30, 40],
            rawText: "技术要求：去除毛刺",
          },
          {
            id: "source-next",
            pageIndex: 1,
            bbox: [50, 60, 70, 80],
            rawText: "125 X 2",
          },
        ]}
        balloons={[]}
        selectedItemId="item-other"
        selectedSourceId="source-next"
        onSelectSource={onSelectSource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("source-source-next").getAttribute("data-selected"))
        .toBe("true");
      expect(scrollIntoView).toHaveBeenCalledWith({
        block: "center",
        inline: "center",
      });
    });
    const locatedSource = scrollIntoView.mock.instances[
      scrollIntoView.mock.instances.length - 1
    ] as Element;
    expect(locatedSource.getAttribute("data-testid")).toBe("source-source-next");

    scrollIntoView.mockClear();
    rerender(
      <PdfWorkspace
        pdfDocument={documentFixture()}
        candidates={[]}
        sources={[
          {
            id: "source-only",
            itemIds: ["item-other"],
            pageIndex: 1,
            bbox: [10, 20, 30, 40],
            rawText: "技术要求：去除毛刺",
          },
          {
            id: "source-next",
            pageIndex: 1,
            bbox: [50, 60, 70, 80],
            rawText: "125 X 2",
          },
        ]}
        balloons={[]}
        selectedSourceId="source-next"
        onSelectSource={onSelectSource}
      />,
    );
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  test("来源定位完成后仍允许手动切换 PDF 页面", async () => {
    render(
      <PdfWorkspace
        pdfDocument={documentFixture()}
        candidates={[]}
        sources={[
          {
            id: "source-only",
            pageIndex: 0,
            bbox: [10, 20, 30, 40],
            rawText: "技术要求：去除毛刺",
          },
        ]}
        balloons={[]}
        selectedSourceId="source-only"
      />,
    );

    await screen.findByTestId("source-source-only");
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await waitFor(() => {
      expect(screen.getByTestId("page-indicator").textContent).toBe("2 / 2");
    });
  });

  test("每个页码按钮渲染独立真实缩略图", async () => {
    const pdfDocument = documentFixture();
    render(
      <PdfWorkspace
        pdfDocument={pdfDocument}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-thumbnail-1").hasAttribute("hidden")).toBe(false);
      expect(screen.getByTestId("pdf-thumbnail-2").hasAttribute("hidden")).toBe(false);
    });
    expect(pdfDocument.getPage).toHaveBeenCalledWith(1);
    expect(pdfDocument.getPage).toHaveBeenCalledWith(2);
  });

  test("单页缩略图失败只显示中文页码 fallback", async () => {
    const pdfDocument: PdfDocumentLike = {
      numPages: 2,
      getPage: vi.fn(async (pageNumber: number) => {
        if (pageNumber === 2) throw new Error("thumbnail failed");
        return {
          getViewport: ({ scale }: { scale: number }) => ({
            width: 100 * scale,
            height: 200 * scale,
          }),
          render: vi.fn(() => ({
            promise: Promise.resolve(),
            cancel: vi.fn(),
          })),
        };
      }),
    };
    render(
      <PdfWorkspace
        pdfDocument={pdfDocument}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );

    expect(await screen.findByText("第 2 页预览不可用")).not.toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("适合页面使用容器尺寸并清零 pan", async () => {
    render(
      <PdfWorkspace
        pdfDocument={rotatedDocumentFixture()}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );
    const frame = screen.getByTestId("pdf-scroll-frame");
    Object.defineProperties(frame, {
      clientWidth: { configurable: true, value: 424 },
      clientHeight: { configurable: true, value: 224 },
    });
    await waitFor(() => {
      expect(screen.getByTestId("pdf-canvas").getAttribute("width")).toBe("200");
    });
    fireEvent.click(screen.getByRole("button", { name: "向右平移" }));
    fireEvent.click(screen.getByRole("button", { name: "适合页面" }));

    expect(screen.getByLabelText("缩放比例").textContent).toBe("200%");
    expect(screen.getByTestId("pdf-page-layer").getAttribute("style")).toContain(
      "transform: translate(0px, 0px)",
    );
  });

  test("提供适合页面、展开和中文图例控件", () => {
    render(
      <PdfWorkspace
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "适合页面" }));
    expect(screen.getByLabelText("缩放比例").textContent).toBe("100%");
    fireEvent.click(screen.getByRole("button", { name: "展开工作区" }));
    expect(screen.getByTestId("pdf-workspace").getAttribute("data-expanded")).toBe("true");
    expect(screen.getByRole("list", { name: "图纸标注图例" }).textContent)
      .toContain("正式气泡候选项来源标注已排除");
  });

  test("图例以同一红色色相区分自动通过空心气泡与正式实心气泡", () => {
    render(
      <PdfWorkspace
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
      />,
    );

    const legend = screen.getByRole("list", { name: "图纸标注图例" });
    expect(legend.textContent).toContain("自动通过");
    expect(legend.textContent).toContain("正式气泡");
    const provisional = legend.querySelector<HTMLElement>(
      "[data-color='auto-accepted']",
    );
    const formal = legend.querySelector<HTMLElement>("[data-color='balloon']");
    expect(provisional?.style.backgroundColor).toBe("transparent");
    expect(formal?.style.backgroundColor).toBe("rgb(220, 38, 38)");
  });

  test("辅助区使用检验、导出与处理文案并在收起后保持挂载", () => {
    render(
      <PdfWorkspace
        pdfDocument={null}
        candidates={[]}
        sources={[]}
        balloons={[]}
        auxiliaryPanel={<div data-testid="auxiliary-content">正式文件</div>}
      />,
    );

    const open = screen.getByRole("button", {
      name: "展开检验、导出与处理信息",
    });
    expect(open.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(open);
    expect(screen.getByRole("button", {
      name: "收起检验、导出与处理信息",
    }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", {
      name: "收起检验、导出与处理信息",
    }));
    expect(screen.getByTestId("auxiliary-content")).not.toBeNull();
  });
});
