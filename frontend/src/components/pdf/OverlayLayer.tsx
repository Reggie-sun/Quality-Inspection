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
const CANDIDATE_MARKER_RADIUS = 10;

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

function clampMarker(value: number, extent: number): number {
  return Math.min(
    Math.max(value, CANDIDATE_MARKER_RADIUS),
    Math.max(CANDIDATE_MARKER_RADIUS, extent - CANDIDATE_MARKER_RADIUS),
  );
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
  const activeBalloonItemIds = new Set(
    balloons
      .filter((balloon) => balloon.status !== "deleted")
      .map((balloon) => balloon.itemId)
      .filter((itemId): itemId is string => itemId !== undefined),
  );
  const candidateMarkerItemIds = new Set<string>();
  const candidateMarkers = candidates.flatMap((item) => {
    if (
      item.itemId === undefined
      || item.candidateNumber === undefined
      || activeBalloonItemIds.has(item.itemId)
      || candidateMarkerItemIds.has(item.itemId)
    ) {
      return [];
    }
    candidateMarkerItemIds.add(item.itemId);
    const [, y0, x1] = transformBox(matrix, item.bbox);
    return [{
      item,
      itemId: item.itemId,
      candidateNumber: item.candidateNumber,
      markerX: clampMarker(x1, pageWidth),
      markerY: clampMarker(y0, pageHeight),
    }];
  });

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
        const itemId = item.itemId ?? item.id;
        const isSelected = selectedRelation(
          { itemId, itemIds: item.itemIds },
          selected,
        );
        const selectCandidate = () => {
          const selectedItem = selectRelationItem(
            { itemId, itemIds: item.itemIds },
            selected,
          );
          if (selectedItem !== undefined) selectItem?.(selectedItem);
        };
        return (
          <g key={item.id}>
            <rect
              data-testid={`candidate-${item.id}`}
              data-selected={isSelected}
              x={x0}
              y={y0}
              width={x1 - x0}
              height={y1 - y0}
              fill="transparent"
              stroke={isSelected ? "#1d4ed8" : "#2563eb"}
              strokeWidth={isSelected ? 3 : 1.5}
              onClick={selectCandidate}
              style={{ cursor: selectItem ? "pointer" : "default" }}
            />
          </g>
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
      {candidateMarkers.map(({
        item,
        itemId,
        candidateNumber,
        markerX,
        markerY,
      }) => {
        const isSelected = selectedRelation(
          { itemId, itemIds: item.itemIds },
          selected,
        );
        const selectCandidate = () => {
          const selectedItem = selectRelationItem(
            { itemId, itemIds: item.itemIds },
            selected,
          );
          if (selectedItem !== undefined) selectItem?.(selectedItem);
        };
        return (
          <g
            key={`candidate-number-${item.id}`}
            data-testid={`candidate-number-${item.id}`}
            data-item-id={itemId}
            data-selected={isSelected}
            role="button"
            aria-label={zhCN.pdf.candidateMarker(candidateNumber)}
            tabIndex={0}
            onClick={selectCandidate}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectCandidate();
              }
            }}
            style={{ cursor: selectItem ? "pointer" : "default" }}
          >
            <circle
              cx={markerX}
              cy={markerY}
              r={CANDIDATE_MARKER_RADIUS}
              fill={isSelected ? "#2563EB" : "#EFF6FF"}
              stroke="#2563EB"
              strokeWidth={isSelected ? 2 : 1.5}
            />
            <text
              x={markerX}
              y={markerY}
              textAnchor="middle"
              dominantBaseline="middle"
              fontFamily="DejaVu Sans"
              fontSize={8}
              fill={isSelected ? "#FFFFFF" : "#2563EB"}
              style={{ pointerEvents: "none" }}
            >
              {candidateNumber}
            </text>
          </g>
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
