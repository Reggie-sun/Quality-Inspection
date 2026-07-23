import { useRef } from "react";

import type { BalloonOverlay as BalloonView, PdfMatrix } from "../../api/types";
import { zhCN } from "../../copy/zhCN";


type MatrixLike = Pick<DOMMatrix, "a" | "b" | "c" | "d" | "e" | "f">;
export const BALLOON_RADIUS_PDF = 12;
const GLYPH_FONT_SIZE_PDF = 9;
const DEJAVU_SANS_DIGIT_ADVANCE_EM = 0.63623046875;
const DEJAVU_SANS_ASCENDER_EM = 0.92822265625;
const DEJAVU_SANS_DESCENDER_EM = -0.23583984375;


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


function invertMatrix(matrix: PdfMatrix): PdfMatrix {
  const [a, b, c, d, e, f] = matrix;
  const determinant = a * d - b * c;
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-9) {
    throw new Error("balloon coordinate matrix is not invertible");
  }
  return [
    d / determinant,
    -b / determinant,
    -c / determinant,
    a / determinant,
    (c * f - d * e) / determinant,
    (b * e - a * f) / determinant,
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


export function balloonGlyphBBox(
  formalNumber: number,
  center: [number, number],
): [number, number, number, number] {
  const text = String(formalNumber);
  const width = Math.max(
    5,
    text.length * DEJAVU_SANS_DIGIT_ADVANCE_EM * GLYPH_FONT_SIZE_PDF,
  );
  const height = (
    DEJAVU_SANS_ASCENDER_EM - DEJAVU_SANS_DESCENDER_EM
  ) * GLYPH_FONT_SIZE_PDF;
  return [
    center[0] - width / 2,
    center[1] - height / 2,
    center[0] + width / 2,
    center[1] + height / 2,
  ];
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
  const radius = balloon.radius ?? BALLOON_RADIUS_PDF;
  const numberText = String(balloon.number);
  const glyphBox = balloonGlyphBBox(balloon.number, displayCenter);
  const displayLeaderTarget = balloon.leaderTarget === undefined
    ? undefined
    : applyMatrix(invertMatrix(renderToPdfMatrix), balloon.leaderTarget);
  const collisionFlags = balloon.collisionFlags ?? [];
  const blocked = balloon.placementStatus === "manual_required" || collisionFlags.length > 0;

  return (
    <g
      data-testid={`balloon-${balloon.id}`}
      data-item-id={balloon.itemId}
      data-selected={selected}
      data-placement-status={balloon.placementStatus ?? "placed"}
      data-collision-flags={collisionFlags.join(",")}
      data-circle={`${displayCenter[0]},${displayCenter[1]},${radius}`}
      data-glyph-bbox={glyphBox.join(",")}
      role="button"
      aria-label={zhCN.balloon.marker(balloon.number, blocked)}
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
      {displayLeaderTarget === undefined ? null : (
        <line
          data-testid={`leader-${balloon.id}`}
          x1={displayCenter[0]}
          y1={displayCenter[1]}
          x2={displayLeaderTarget[0]}
          y2={displayLeaderTarget[1]}
          stroke={blocked ? "#b91c1c" : "#334155"}
          strokeWidth={1.1}
          style={{ pointerEvents: "none" }}
        />
      )}
      <circle
        cx={displayCenter[0]}
        cy={displayCenter[1]}
        r={radius}
        fill={blocked ? "#fff1f2" : "white"}
        stroke={selected ? "#2563eb" : blocked ? "#b91c1c" : "#dc2626"}
        strokeWidth={selected ? 3 : 1.5}
      />
      <text
        x={displayCenter[0]}
        y={displayCenter[1]}
        textAnchor="middle"
        dominantBaseline="middle"
        fontFamily="DejaVu Sans"
        fontSize={GLYPH_FONT_SIZE_PDF}
        fontWeight={400}
        fill={blocked ? "#991b1b" : "#0f172a"}
        style={{ pointerEvents: "none" }}
      >
        {numberText}
      </text>
    </g>
  );
}
