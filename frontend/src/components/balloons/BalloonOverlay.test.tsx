import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  BalloonOverlay,
  clientToPdf,
  displayToPdfMatrix,
} from "./BalloonOverlay";
import { BalloonToolbar } from "./BalloonToolbar";


afterEach(cleanup);

describe("BalloonOverlay", () => {
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
  fireEvent.click(screen.getByRole("button", { name: "Delete balloon" }));
  fireEvent.click(screen.getByRole("button", { name: "Rebuild balloon" }));
  fireEvent.click(screen.getByRole("button", { name: "Move balloon later" }));
  fireEvent.click(screen.getByRole("button", { name: "Renumber balloons" }));

  expect(onDelete).toHaveBeenCalledWith("b1", 4);
  expect(onRebuild).toHaveBeenCalledWith("b1", 4);
  expect(onReorder).toHaveBeenCalledWith("b1", 4, 1);
  expect(onRenumber).toHaveBeenCalledWith(["b1"], { b1: 4 });
});
