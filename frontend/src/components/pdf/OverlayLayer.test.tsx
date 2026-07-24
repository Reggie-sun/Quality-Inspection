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
    expect(screen.getByRole("button", { name: "气泡 7" })).not.toBeNull();

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
});
