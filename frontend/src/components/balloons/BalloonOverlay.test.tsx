import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  BalloonOverlay,
  balloonGlyphBBox,
  clientToPdf,
  displayToPdfMatrix,
} from "./BalloonOverlay";
import { BalloonToolbar } from "./BalloonToolbar";


afterEach(cleanup);

describe("BalloonOverlay", () => {
  test("P0-BAL-006 uses the approved DejaVu Sans digit metrics", () => {
    const [x0, y0, x1, y1] = balloonGlyphBBox(272, [100, 100]);

    expect(x1 - x0).toBeCloseTo(3 * 0.63623046875 * 9);
    expect(y1 - y0).toBeCloseTo((0.92822265625 + 0.23583984375) * 9);
  });

  test("P0-BAL-006 persists rotated-page PDF coordinates rather than CSS pixels", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    Object.defineProperty(svg, "getScreenCTM", {
      configurable: true,
      value: () => ({
        inverse: () => ({ a: 0.5, b: 0, c: 0, d: 0.5, e: -5, f: -10 }),
      }),
    });

    const effectiveRenderToPdf = displayToPdfMatrix(
      [0, 2, -2, 0, 400, 0],
      [0, -0.5, 0.5, 0, 0, 200],
    );
    expect(effectiveRenderToPdf).toEqual([0, -1, 1, 0, 0, 200]);
    expect(clientToPdf(svg, 110, 70, effectiveRenderToPdf)).toEqual([25, 150]);
  });

  test("P0-BAL-006 drag emits one explicit move with PDF coordinates", () => {
    const onMove = vi.fn();
    render(
      <svg aria-label="test overlay">
        <BalloonOverlay
          balloon={{
            id: "b1",
            itemId: "i1",
            sourceId: "s1",
            pageIndex: 0,
            center: [50, 60],
            number: 1,
            version: 4,
            status: "active",
            sortOrder: 0,
          }}
          renderToPdfMatrix={[1, 0, 0, 1, 0, 0]}
          selected
          onSelect={vi.fn()}
          onMove={onMove}
        />
      </svg>,
    );
    const overlay = screen.getByTestId("balloon-b1") as unknown as SVGGElement;
    expect(overlay.getAttribute("data-item-id")).toBe("i1");
    const owner = overlay.ownerSVGElement;
    if (owner === null) throw new Error("missing owner SVG");
    Object.defineProperty(owner, "getScreenCTM", {
      configurable: true,
      value: () => ({
        inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: -10, f: -20 }),
      }),
    });
    Object.defineProperty(overlay, "setPointerCapture", {
      configurable: true,
      value: vi.fn(),
    });

    const pointerDown = new Event("pointerdown", { bubbles: true });
    Object.defineProperties(pointerDown, {
      pointerId: { value: 7 },
      clientX: { value: 10 },
      clientY: { value: 20 },
    });
    fireEvent(overlay, pointerDown);
    const pointerUp = new Event("pointerup", { bubbles: true });
    Object.defineProperties(pointerUp, {
      pointerId: { value: 7 },
      clientX: { value: 110 },
      clientY: { value: 70 },
    });
    fireEvent(overlay, pointerUp);

    expect(onMove).toHaveBeenCalledWith("b1", 4, [100, 50]);
    expect(onMove).not.toHaveBeenCalledWith("b1", 4, [110, 70]);
  });

  test("P0-BAL-013 selection without drag does not persist a move", () => {
    const onMove = vi.fn();
    const onSelect = vi.fn();
    render(
      <svg aria-label="test overlay">
        <BalloonOverlay
          balloon={{
            id: "b1",
            itemId: "i1",
            sourceId: "s1",
            pageIndex: 0,
            center: [50, 60],
            number: 1,
            version: 4,
            status: "active",
            sortOrder: 0,
          }}
          renderToPdfMatrix={[1, 0, 0, 1, 0, 0]}
          selected={false}
          onSelect={onSelect}
          onMove={onMove}
        />
      </svg>,
    );
    const overlay = screen.getByTestId("balloon-b1") as unknown as SVGGElement;
    const owner = overlay.ownerSVGElement;
    if (owner === null) throw new Error("missing owner SVG");
    Object.defineProperty(owner, "getScreenCTM", {
      configurable: true,
      value: () => ({
        inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }),
      }),
    });
    for (const eventName of ["pointerdown", "pointerup"]) {
      const pointer = new Event(eventName, { bubbles: true });
      Object.defineProperties(pointer, {
        pointerId: { value: 7 },
        clientX: { value: 50 },
        clientY: { value: 60 },
      });
      fireEvent(overlay, pointer);
    }

    expect(onSelect).toHaveBeenCalledWith("i1", "b1");
    expect(onMove).not.toHaveBeenCalled();
  });

  test("越出页面的气泡仍可通过可见引线拖回合法位置", () => {
    const onMove = vi.fn();
    render(
      <svg aria-label="test overlay">
        <BalloonOverlay
          balloon={{
            id: "outside-balloon",
            itemId: "outside-item",
            sourceId: "outside-source",
            pageIndex: 0,
            center: [50, 120],
            leaderTarget: [50, 80],
            number: 12,
            version: 3,
            status: "active",
            sortOrder: 11,
            placementStatus: "manual_required",
            collisionFlags: ["outside_cropbox"],
          }}
          renderToPdfMatrix={[1, 0, 0, 1, 0, 0]}
          selected
          onSelect={vi.fn()}
          onMove={onMove}
        />
      </svg>,
    );
    const overlay = screen.getByTestId(
      "balloon-outside-balloon",
    ) as unknown as SVGGElement;
    const leader = screen.getByTestId("leader-outside-balloon");
    expect(leader.style.pointerEvents).toBe("stroke");
    const owner = overlay.ownerSVGElement;
    if (owner === null) throw new Error("missing owner SVG");
    Object.defineProperty(owner, "getScreenCTM", {
      configurable: true,
      value: () => ({
        inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }),
      }),
    });
    Object.defineProperty(overlay, "setPointerCapture", {
      configurable: true,
      value: vi.fn(),
    });

    for (const [eventName, clientY] of [
      ["pointerdown", 100],
      ["pointerup", 70],
    ] as const) {
      const pointer = new Event(eventName, { bubbles: true });
      Object.defineProperties(pointer, {
        pointerId: { value: 9 },
        clientX: { value: 50 },
        clientY: { value: clientY },
      });
      fireEvent(leader, pointer);
    }

    expect(onMove).toHaveBeenCalledWith("outside-balloon", 3, [50, 70]);
  });

  test("P0-UI-004 renders leaders and backend collision state without cross-balloon overlap", () => {
    const balloons = [
      {
        id: "b1",
        itemId: "i1",
        sourceId: "s1",
        pageIndex: 0,
        center: [30, 30] as [number, number],
        number: 1,
        version: 1,
        status: "active" as const,
        sortOrder: 0,
        placementStatus: "placed" as const,
        collisionFlags: [] as string[],
        leaderTarget: [15, 15] as [number, number],
      },
      {
        id: "b2",
        itemId: "i2",
        sourceId: "s2",
        pageIndex: 0,
        center: [70, 30] as [number, number],
        number: 2,
        version: 1,
        status: "active" as const,
        sortOrder: 1,
        placementStatus: "manual_required" as const,
        collisionFlags: ["protected_overlap"],
        leaderTarget: [85, 15] as [number, number],
      },
    ];
    render(
      <svg aria-label="dense balloon overlay">
        {balloons.map((balloon) => (
          <BalloonOverlay
            key={balloon.id}
            balloon={balloon}
            renderToPdfMatrix={[1, 0, 0, 1, 0, 0]}
            selected={false}
            onSelect={vi.fn()}
            onMove={vi.fn()}
          />
        ))}
      </svg>,
    );

    const first = screen.getByTestId("balloon-b1");
    const second = screen.getByTestId("balloon-b2");
    expect(screen.getByTestId("leader-b1")).not.toBeNull();
    expect(screen.getByTestId("leader-b2")).not.toBeNull();
    expect(first.getAttribute("data-placement-status")).toBe("placed");
    expect(second.getAttribute("data-placement-status")).toBe("manual_required");
    expect(second.getAttribute("data-collision-flags")).toBe("protected_overlap");

    const circle = (element: HTMLElement) =>
      (element.getAttribute("data-circle") ?? "").split(",").map(Number);
    const glyph = (element: HTMLElement) =>
      (element.getAttribute("data-glyph-bbox") ?? "").split(",").map(Number);
    const [x1, y1, r1] = circle(first);
    const [x2, y2, r2] = circle(second);
    const [gx0, gy0, gx1, gy1] = glyph(first);
    const [hx0, hy0, hx1, hy1] = glyph(second);

    expect(Math.hypot(x1 - x2, y1 - y2)).toBeGreaterThanOrEqual(r1 + r2);
    expect(gx1 <= hx0 || hx1 <= gx0 || gy1 <= hy0 || hy1 <= gy0).toBe(true);
    expect(Math.hypot(gx0 - x1, gy0 - y1)).toBeLessThan(r1);
    expect(Math.hypot(gx1 - x1, gy1 - y1)).toBeLessThan(r1);
    expect(Math.hypot(hx0 - x2, hy0 - y2)).toBeLessThan(r2);
    expect(Math.hypot(hx1 - x2, hy1 - y2)).toBeLessThan(r2);
  });
});

test("P0-BAL-009/010/011/012 toolbar exposes balloon commands explicitly", () => {
  const onDelete = vi.fn();
  const onRebuild = vi.fn();
  const onReorder = vi.fn();
  const onRenumber = vi.fn();
  render(
    <BalloonToolbar
      balloons={[
        {
          id: "b1",
          itemId: "i1",
          sourceId: "s1",
          pageIndex: 0,
          center: [50, 60],
          number: 1,
          version: 4,
          status: "active",
          sortOrder: 0,
        },
      ]}
      selectedBalloonId="b1"
      onDelete={onDelete}
      onRebuild={onRebuild}
      onReorder={onReorder}
      onRenumber={onRenumber}
    />,
  );

  expect(onDelete).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "删除气泡" }));
  fireEvent.click(screen.getByRole("button", { name: "重建气泡" }));
  fireEvent.click(screen.getByRole("button", { name: "气泡后移" }));
  fireEvent.click(screen.getByRole("button", { name: "重新编号" }));

  expect(onDelete).toHaveBeenCalledWith("b1", 4);
  expect(onRebuild).toHaveBeenCalledWith("b1", 4);
  expect(onReorder).toHaveBeenCalledWith("b1", 4, 1);
  expect(onRenumber).toHaveBeenCalledWith(["b1"], { b1: 4 });
});
