import { useRef } from "react";

import type { BalloonOverlay as BalloonView, PdfMatrix } from "../../api/types";


type MatrixLike = Pick<DOMMatrix, "a" | "b" | "c" | "d" | "e" | "f">;


function applyMatrix(matrix: MatrixLike | PdfMatrix, point: [number, number]): [number, number] {
  const values: PdfMatrix = Array.isArray(matrix)
    ? matrix
    : [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f];
  const [a, b, c, d, e, f] = values;
  return [
    a * point[0] + c * point[1] + e,
    b * point[0] + d * point[1] + f,
  ];
}


export function displayToPdfMatrix(
  pdfToRenderMatrix: PdfMatrix,
  renderToPdfMatrix: PdfMatrix,
): PdfMatrix {
  const renderScale = Math.hypot(pdfToRenderMatrix[0], pdfToRenderMatrix[1]);
  if (!Number.isFinite(renderScale) || renderScale <= 0) {
    throw new Error("PDF-to-render matrix must have a positive finite scale");
  }
  return [
    renderToPdfMatrix[0] * renderScale,
    renderToPdfMatrix[1] * renderScale,
    renderToPdfMatrix[2] * renderScale,
    renderToPdfMatrix[3] * renderScale,
    renderToPdfMatrix[4],
    renderToPdfMatrix[5],
  ];
}


export function clientToPdf(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
  renderToPdfMatrix: PdfMatrix,
): [number, number] {
  const screenMatrix = svg.getScreenCTM();
  if (screenMatrix === null) throw new Error("overlay transform unavailable");
  const renderPoint = applyMatrix(screenMatrix.inverse(), [clientX, clientY]);
  return applyMatrix(renderToPdfMatrix, renderPoint);
}


type BalloonOverlayProps = {
  balloon: BalloonView;
  renderToPdfMatrix: PdfMatrix;
  displayCenter?: [number, number];
  selected: boolean;
  onSelect: (itemId: string, balloonId: string) => void;
  onMove: (
    balloonId: string,
    expectedVersion: number,
    centerPdf: [number, number],
  ) => void;
};


export function BalloonOverlay({
  balloon,
  renderToPdfMatrix,
  displayCenter = balloon.center,
  selected,
  onSelect,
  onMove,
}: BalloonOverlayProps) {
  const pointerStart = useRef<
    { pointerId: number; clientX: number; clientY: number } | undefined
  >(undefined);
  const select = () => onSelect(balloon.itemId ?? balloon.id, balloon.id);

  return (
    <g
      data-testid={`balloon-${balloon.id}`}
      data-selected={selected}
      role="button"
      aria-label={`Balloon ${balloon.number}`}
      tabIndex={0}
      onClick={select}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") select();
      }}
      onPointerDown={(event) => {
        select();
        pointerStart.current = {
          pointerId: event.pointerId,
          clientX: event.clientX,
          clientY: event.clientY,
        };
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerUp={(event) => {
        const start = pointerStart.current;
        pointerStart.current = undefined;
        if (
          start === undefined || start.pointerId !== event.pointerId ||
          Math.hypot(event.clientX - start.clientX, event.clientY - start.clientY) < 3
        ) return;
        const svg = event.currentTarget.ownerSVGElement;
        if (svg === null || balloon.version === undefined) return;
        onMove(
          balloon.id,
          balloon.version,
          clientToPdf(svg, event.clientX, event.clientY, renderToPdfMatrix),
        );
      }}
      onPointerCancel={() => {
        pointerStart.current = undefined;
      }}
      style={{ cursor: "grab" }}
    >
      <circle
        cx={displayCenter[0]}
        cy={displayCenter[1]}
        r={10}
        fill="white"
        stroke={selected ? "#7c3aed" : "#dc2626"}
        strokeWidth={selected ? 3 : 1.5}
      />
      <text
        x={displayCenter[0]}
        y={displayCenter[1]}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={10}
        style={{ pointerEvents: "none" }}
      >
        {balloon.number}
      </text>
    </g>
  );
}
