import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { OverlayLayer } from "./OverlayLayer";


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
    expect(screen.getByLabelText("engineering overlays").getAttribute("viewBox")).toBe(
      "0 0 100 200",
    );
    expect(screen.getByLabelText("engineering overlays").getAttribute("width")).toBe(
      "200",
    );
    expect(candidate.getAttribute("data-selected")).toBe("true");
  });
});
