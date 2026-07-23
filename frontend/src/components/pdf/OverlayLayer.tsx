import type {
  BalloonOverlay,
  OverlayBox,
  PdfCoordinates,
  PdfMatrix,
} from "../../api/types";
import {
  BalloonOverlay as BalloonMarker,
  displayToPdfMatrix,
} from "../balloons/BalloonOverlay";
import { zhCN } from "../../copy/zhCN";
import { selectRelationItem, selectedRelation } from "../workbench/selection";


const IDENTITY_MATRIX: PdfMatrix = [1, 0, 0, 1, 0, 0];

function normalizeMatrix(matrix: PdfMatrix): PdfMatrix {
  const matrixScale = Math.hypot(matrix[0], matrix[1]);
  if (!Number.isFinite(matrixScale) || matrixScale <= 0) {
    throw new Error("PDF-to-render matrix must have a positive finite scale");
  }
  return matrix.map((value) => value / matrixScale) as PdfMatrix;
}

function transformPoint(matrix: PdfMatrix, point: [number, number]): [number, number] {
  const [a, b, c, d, e, f] = matrix;
  const [x, y] = point;
  return [a * x + c * y + e, b * x + d * y + f];
}

function transformBox(matrix: PdfMatrix, bbox: PdfCoordinates): PdfCoordinates {
  const [x0, y0, x1, y1] = bbox;
  const corners = [
    transformPoint(matrix, [x0, y0]),
    transformPoint(matrix, [x1, y0]),
    transformPoint(matrix, [x0, y1]),
    transformPoint(matrix, [x1, y1]),
  ];
  const xs = corners.map(([x]) => x);
  const ys = corners.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}


type OverlayLayerProps = {
  pageWidth: number;
  pageHeight: number;
  scale: number;
  candidates: OverlayBox[];
  sources: OverlayBox[];
  balloons: BalloonOverlay[];
  pdfToRenderMatrix?: PdfMatrix;
  renderToPdfMatrix?: PdfMatrix;
  selectedItemId?: string;
  selectedSourceId?: string;
  selectedBalloonId?: string;
  onSelectItem?: (itemId: string) => void;
  onSelectSource?: (sourceId: string) => void;
  onSelectBalloon?: (itemId: string, balloonId: string) => void;
  onMoveBalloon?: (
    balloonId: string,
    expectedVersion: number,
    centerPdf: [number, number],
  ) => void;
  selectedId?: string;
  onSelect?: (id: string) => void;
};


export function OverlayLayer({
  pageWidth,
  pageHeight,
  scale,
  candidates,
  sources,
  balloons,
  pdfToRenderMatrix = IDENTITY_MATRIX,
  renderToPdfMatrix = IDENTITY_MATRIX,
  selectedItemId,
  selectedSourceId,
  selectedBalloonId,
  onSelectItem,
  onSelectSource,
  onSelectBalloon,
  onMoveBalloon,
  selectedId,
  onSelect,
}: OverlayLayerProps) {
  const matrix = normalizeMatrix(pdfToRenderMatrix);
  const effectiveRenderToPdfMatrix = displayToPdfMatrix(
    pdfToRenderMatrix,
    renderToPdfMatrix,
  );
  const selected = selectedItemId ?? selectedId;
  const selectItem = onSelectItem ?? onSelect;

  return (
    <svg
      aria-label={zhCN.pdf.overlay}
      data-scale={scale}
      width={pageWidth * scale}
      height={pageHeight * scale}
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      style={{ position: "absolute", inset: 0 }}
    >
      {candidates.map((item) => {
        const [x0, y0, x1, y1] = transformBox(matrix, item.bbox);
        const isSelected = selectedRelation(
          { itemId: item.itemId ?? item.id, itemIds: item.itemIds },
          selected,
        );
        return (
          <rect
            key={item.id}
            data-testid={`candidate-${item.id}`}
            data-selected={isSelected}
            x={x0}
            y={y0}
            width={x1 - x0}
            height={y1 - y0}
            fill="transparent"
            stroke={isSelected ? "#1d4ed8" : "#2563eb"}
            strokeWidth={isSelected ? 3 : 1.5}
            onClick={() => {
              const itemId = selectRelationItem(
                { itemId: item.itemId ?? item.id, itemIds: item.itemIds },
                selected,
              );
              if (itemId !== undefined) selectItem?.(itemId);
            }}
            style={{ cursor: selectItem ? "pointer" : "default" }}
          />
        );
      })}
      {sources.map((item) => {
        const [x0, y0, x1, y1] = transformBox(matrix, item.bbox);
        const isSelected = selectedRelation(
          { itemId: item.itemId, itemIds: item.itemIds },
          selected,
        ) || item.id === selectedSourceId;
        return (
          <rect
            key={item.id}
            data-testid={`source-${item.id}`}
            data-selected={isSelected}
            x={x0}
            y={y0}
            width={x1 - x0}
            height={y1 - y0}
            fill="transparent"
            stroke={isSelected ? "#0e7490" : "#0891b2"}
            strokeDasharray="4 3"
            strokeWidth={1.5}
            onClick={() => {
              const itemId = selectRelationItem(item, selected);
              if (itemId !== undefined) {
                selectItem?.(itemId);
                return;
              }
              onSelectSource?.(item.id);
            }}
            style={{ cursor: selectItem || onSelectSource ? "pointer" : "default" }}
          />
        );
      })}
      {balloons.map((item) => {
        const [x, y] = transformPoint(matrix, item.center);
        return (
          <BalloonMarker
            key={item.id}
            balloon={item}
            displayCenter={[x, y]}
            renderToPdfMatrix={effectiveRenderToPdfMatrix}
            selected={
              selectedBalloonId === item.id ||
              selectedRelation({ itemId: item.itemId ?? item.id }, selected)
            }
            onSelect={(itemId, balloonId) => {
              selectItem?.(itemId);
              onSelectBalloon?.(itemId, balloonId);
            }}
            onMove={onMoveBalloon ?? (() => undefined)}
          />
        );
      })}
    </svg>
  );
}
