import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { OverlayLayer } from "./OverlayLayer";

afterEach(cleanup);

describe("OverlayLayer", () => {
  test("P0-UI-004 renders candidate, source and balloon layers", () => {
    const onSelect = vi.fn();
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={200}
        scale={2}
        selectedId="c1"
        onSelect={onSelect}
        candidates={[{ id: "c1", bbox: [10, 20, 30, 40] }]}
        sources={[{ id: "s1", bbox: [40, 50, 60, 70] }]}
        balloons={[{ id: "b1", center: [80, 90], number: 1 }]}
      />,
    );

    const candidate = screen.getByTestId("candidate-c1");
    const source = screen.getByTestId("source-s1");
    const balloon = screen.getByTestId("balloon-b1");
    expect(candidate).not.toBeNull();
    expect(source).not.toBeNull();
    expect(balloon).not.toBeNull();
    expect(source.style.cursor).toBe("pointer");
    expect(balloon.getAttribute("role")).toBe("button");
    expect(screen.getByLabelText("工程图纸标注层").getAttribute("viewBox")).toBe(
      "0 0 100 200",
    );
    expect(screen.getByLabelText("工程图纸标注层").getAttribute("width")).toBe(
      "200",
    );
    expect(candidate.getAttribute("data-selected")).toBe("true");
  });

  test("候选气泡显示在首个候选框并可通过鼠标和键盘选择", () => {
    const onSelectItem = vi.fn();
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[
          {
            id: "candidate-first",
            itemId: "item-1",
            bbox: [90, 0, 110, 20],
            candidateNumber: 3,
          },
          {
            id: "candidate-duplicate",
            itemId: "item-1",
            bbox: [20, 30, 40, 50],
            candidateNumber: 3,
          },
        ]}
        sources={[]}
        balloons={[]}
        onSelectItem={onSelectItem}
      />,
    );

    const markers = screen.getAllByRole("button", { name: "候选气泡 3" });
    expect(markers).toHaveLength(1);
    expect(markers[0].getAttribute("data-testid")).toBe(
      "candidate-number-candidate-first",
    );
    const edgeCircle = markers[0].querySelector("circle")!;
    expect(Number(edgeCircle.getAttribute("cx"))).toBeGreaterThanOrEqual(11);
    expect(Number(edgeCircle.getAttribute("cx"))).toBeLessThanOrEqual(89);
    expect(Number(edgeCircle.getAttribute("cy"))).toBeGreaterThanOrEqual(11);
    expect(Number(edgeCircle.getAttribute("cy"))).toBeLessThanOrEqual(89);
    const edgeLeader = screen.getByTestId("candidate-leader-candidate-first");
    expect(Math.hypot(
      Number(edgeLeader.getAttribute("x2")) - Number(edgeLeader.getAttribute("x1")),
      Number(edgeLeader.getAttribute("y2")) - Number(edgeLeader.getAttribute("y1")),
    )).toBeGreaterThanOrEqual(15);

    fireEvent.click(markers[0]);
    fireEvent.keyDown(markers[0], { key: "Enter" });
    fireEvent.keyDown(markers[0], { key: " " });

    expect(onSelectItem).toHaveBeenNthCalledWith(1, "item-1");
    expect(onSelectItem).toHaveBeenNthCalledWith(2, "item-1");
    expect(onSelectItem).toHaveBeenNthCalledWith(3, "item-1");
  });

  test("大量候选和正式气泡仅保留当前项进入 Tab 顺序", () => {
    render(
      <OverlayLayer
        pageWidth={200}
        pageHeight={200}
        scale={1}
        candidates={[
          {
            id: "candidate-1",
            itemId: "item-1",
            bbox: [20, 20, 40, 40],
            candidateNumber: 1,
          },
          {
            id: "candidate-2",
            itemId: "item-2",
            bbox: [80, 20, 100, 40],
            candidateNumber: 2,
          },
        ]}
        sources={[]}
        balloons={[
          {
            id: "balloon-3",
            itemId: "item-3",
            center: [40, 120],
            number: 3,
            status: "active",
          },
          {
            id: "balloon-4",
            itemId: "item-4",
            center: [100, 120],
            number: 4,
            status: "active",
          },
        ]}
        selectedItemId="item-2"
        onSelectItem={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "候选气泡 1" })
      .getAttribute("tabindex")).toBe("-1");
    expect(screen.getByRole("button", { name: "候选气泡 2" })
      .getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("button", { name: "正式气泡 3" })
      .getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("button", { name: "正式气泡 4" })
      .getAttribute("tabindex")).toBe("-1");
  });

  test("没有移动权限时正式气泡仍可选择但不呈现可拖动状态", () => {
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[]}
        sources={[]}
        balloons={[{
          id: "reviewed-balloon",
          itemId: "reviewed-item",
          center: [50, 50],
          number: 1,
          version: 3,
          status: "active",
        }]}
        selectedItemId="reviewed-item"
        onSelectItem={vi.fn()}
      />,
    );

    const balloon = screen.getByRole("button", { name: "正式气泡 1" });
    expect(balloon.style.cursor).toBe("pointer");
    expect(balloon.getAttribute("data-read-only")).toBe("true");
  });

  test("候选气泡优先放在候选框外且相邻序号不会互相重叠", () => {
    render(
      <OverlayLayer
        pageWidth={200}
        pageHeight={200}
        scale={1}
        candidates={[
          {
            id: "candidate-near-1",
            itemId: "item-1",
            bbox: [50, 50, 80, 70],
            candidateNumber: 1,
          },
          {
            id: "candidate-near-2",
            itemId: "item-2",
            bbox: [52, 52, 82, 72],
            candidateNumber: 2,
          },
        ]}
        sources={[]}
        balloons={[]}
      />,
    );

    const firstCircle = screen.getByRole("button", { name: "候选气泡 1" })
      .querySelector("circle")!;
    const secondCircle = screen.getByRole("button", { name: "候选气泡 2" })
      .querySelector("circle")!;
    const firstX = Number(firstCircle.getAttribute("cx"));
    const firstY = Number(firstCircle.getAttribute("cy"));
    const secondX = Number(secondCircle.getAttribute("cx"));
    const secondY = Number(secondCircle.getAttribute("cy"));

    expect(firstX).toBeGreaterThan(80);
    expect(firstY).toBeLessThan(50);
    expect(Math.hypot(secondX - firstX, secondY - firstY)).toBeGreaterThanOrEqual(20);
  });

  test("候选气泡使用黑色箭头指向对应候选框", () => {
    render(
      <OverlayLayer
        pageWidth={200}
        pageHeight={200}
        scale={1}
        candidates={[{
          id: "candidate-with-leader",
          itemId: "item-1",
          bbox: [50, 50, 80, 70],
          candidateNumber: 1,
        }]}
        sources={[]}
        balloons={[]}
      />,
    );

    const leader = screen.getByTestId("candidate-leader-candidate-with-leader");
    expect(leader.getAttribute("x1")).toBe("92");
    expect(leader.getAttribute("y1")).toBe("38");
    expect(leader.getAttribute("x2")).toBe("80");
    expect(leader.getAttribute("y2")).toBe("50");
    expect(leader.getAttribute("stroke")).toBe("#111111");
    expect(leader.getAttribute("marker-end")).toBe("url(#candidate-arrowhead)");
    expect(leader.getAttribute("aria-hidden")).toBe("true");
    expect(
      screen.getByRole("button", { name: "候选气泡 1" }).contains(leader),
    ).toBe(false);
  });

  test("候选气泡位于来源标注之后并在重叠时保持可选择", () => {
    const onSelectItem = vi.fn();
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[{
          id: "candidate-overlap",
          itemId: "item-1",
          bbox: [10, 20, 30, 40],
          candidateNumber: 1,
        }]}
        sources={[{
          id: "source-overlap",
          itemId: "item-1",
          bbox: [20, 10, 40, 30],
        }]}
        balloons={[]}
        onSelectItem={onSelectItem}
      />,
    );

    const source = screen.getByTestId("source-source-overlap");
    const marker = screen.getByRole("button", { name: "候选气泡 1" });
    expect(source.compareDocumentPosition(marker) & Node.DOCUMENT_POSITION_FOLLOWING)
      .not.toBe(0);

    fireEvent.click(marker);
    expect(onSelectItem).toHaveBeenCalledWith("item-1");
  });

  test("缺少 itemId 时只显示候选框，不显示候选序号", () => {
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[{
          id: "candidate-without-item",
          bbox: [10, 20, 30, 40],
          candidateNumber: 1,
        }]}
        sources={[]}
        balloons={[]}
      />,
    );

    expect(screen.getByTestId("candidate-candidate-without-item")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "候选气泡 1" })).toBeNull();
  });

  test("有效正式气泡抑制候选气泡，已删除正式气泡不抑制", () => {
    const candidate = {
      id: "candidate-1",
      itemId: "item-1",
      bbox: [10, 20, 30, 40] as [number, number, number, number],
      candidateNumber: 1,
    };
    const { rerender } = render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[candidate]}
        sources={[]}
        balloons={[{
          id: "balloon-active",
          itemId: "item-1",
          center: [50, 60],
          number: 7,
          status: "active",
        }]}
      />,
    );

    expect(screen.queryByRole("button", { name: "候选气泡 1" })).toBeNull();
    expect(screen.getByRole("button", { name: "正式气泡 7" })).not.toBeNull();

    rerender(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[candidate]}
        sources={[]}
        balloons={[{
          id: "balloon-deleted",
          itemId: "item-1",
          center: [50, 60],
          number: 7,
          status: "deleted",
        }]}
      />,
    );

    const restoredCandidate = screen.getByRole("button", { name: "候选气泡 1" });
    expect(restoredCandidate).not.toBeNull();
    expect(restoredCandidate.getAttribute("tabindex")).toBeNull();
    expect(screen.getByTestId("candidate-leader-candidate-1")).not.toBeNull();
    expect(screen.queryByTestId("balloon-balloon-deleted")).toBeNull();
  });

  test("无需气泡项保留候选定位框和序号数据但隐藏画布圆圈与引线", () => {
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[{
          id: "candidate-no-balloon",
          itemId: "item-no-balloon",
          bbox: [10, 20, 30, 40],
          candidateNumber: 66,
          showCandidateMarker: false,
        }]}
        sources={[]}
        balloons={[]}
      />,
    );

    expect(screen.getByTestId("candidate-candidate-no-balloon")).not.toBeNull();
    expect(Boolean(document.querySelector(
      "[data-testid='candidate-number-candidate-no-balloon']",
    ))).toBe(false);
    expect(Boolean(document.querySelector(
      "[data-testid='candidate-leader-candidate-no-balloon']",
    ))).toBe(false);
  });

  test("非选中候选与来源提供可聚焦的密度层级 class", () => {
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[{
          id: "c1",
          itemId: "item-1",
          candidateNumber: 1,
          bbox: [10, 10, 30, 30],
        }]}
        sources={[{
          id: "s1",
          itemId: "item-1",
          bbox: [10, 10, 30, 30],
        }]}
        balloons={[]}
        onSelectItem={vi.fn()}
      />,
    );

    expect(screen.getByTestId("candidate-c1").classList.contains(
      "pdf-overlay-candidate",
    )).toBe(true);
    expect(screen.getByTestId("source-s1").classList.contains(
      "pdf-overlay-source",
    )).toBe(true);
    const marker = screen.getByTestId("candidate-number-c1");
    expect(marker.classList.contains("pdf-overlay-candidate-marker")).toBe(true);
    expect(marker.getAttribute("data-selected")).toBe("false");
  });

  test("仅精确 auto_accepted 后端投影使用红色待统一编号气泡", () => {
    const candidates = [
      {
        id: "auto-candidate",
        itemId: "auto-item",
        candidateNumber: 1,
        bbox: [10, 10, 30, 30] as [number, number, number, number],
        confidenceBand: "high" as const,
        reviewDisposition: "auto_accepted" as const,
        status: "auto_accepted",
        autoAccepted: true,
      },
      {
        id: "unknown-candidate",
        itemId: "unknown-item",
        candidateNumber: 2,
        bbox: [60, 10, 80, 30] as [number, number, number, number],
        confidenceBand: "future_band" as never,
        reviewDisposition: "future_disposition" as never,
        status: "future_status",
      },
      {
        id: "unknown-band-candidate",
        itemId: "unknown-band-item",
        candidateNumber: 3,
        bbox: [60, 60, 80, 80] as [number, number, number, number],
        confidenceBand: "future_band" as never,
        reviewDisposition: "auto_accepted" as const,
        status: "auto_accepted",
      },
    ];
    const { rerender } = render(
      <OverlayLayer
        pageWidth={120}
        pageHeight={100}
        scale={1}
        candidates={candidates}
        sources={[]}
        balloons={[]}
        onSelectItem={vi.fn()}
      />,
    );

    const auto = screen.getByRole("button", {
      name: "自动通过气泡 1，待统一编号",
    });
    const autoCircle = auto.querySelector("circle")!;
    expect(autoCircle.getAttribute("fill")).toBe("transparent");
    expect(autoCircle.getAttribute("stroke")).toBe("#c23b3b");
    expect(auto.querySelector("text")?.getAttribute("fill")).toBe("#c23b3b");

    const unknown = screen.getByRole("button", { name: "候选气泡 2" });
    expect(unknown.querySelector("circle")?.getAttribute("stroke")).toBe("#2563EB");
    const unknownBand = screen.getByRole("button", { name: "候选气泡 3" });
    expect(unknownBand.querySelector("circle")?.getAttribute("stroke"))
      .toBe("#2563EB");

    rerender(
      <OverlayLayer
        pageWidth={120}
        pageHeight={100}
        scale={1}
        candidates={candidates}
        sources={[]}
        balloons={[]}
        selectedItemId="auto-item"
        onSelectItem={vi.fn()}
      />,
    );
    const selectedAuto = screen.getByRole("button", {
      name: "自动通过气泡 1，待统一编号",
    });
    expect(selectedAuto.querySelector("circle")?.getAttribute("fill")).toBe("#c23b3b");
    expect(selectedAuto.querySelector("text")?.getAttribute("fill")).toBe("#FFFFFF");
  });

  test("正式 Balloon projection 继续使用既有正式样式与可访问名称", () => {
    render(
      <OverlayLayer
        pageWidth={100}
        pageHeight={100}
        scale={1}
        candidates={[]}
        sources={[]}
        balloons={[{
          id: "formal-balloon",
          itemId: "formal-item",
          center: [50, 50],
          number: 7,
          status: "active",
        }]}
      />,
    );

    const formal = screen.getByRole("button", { name: "正式气泡 7" });
    expect(formal.getAttribute("data-testid")).toBe("balloon-formal-balloon");
    expect(formal.querySelector("circle")?.getAttribute("stroke")).toBe("#dc2626");
  });
});
