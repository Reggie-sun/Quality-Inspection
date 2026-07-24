import { Fragment } from "react";
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
const CANDIDATE_MARKER_GAP = 2;
const CANDIDATE_MARKER_INSET = 1;

type MarkerPoint = {
  x: number;
  y: number;
};

type MarkerObstacle = {
  id: string;
  kind: "candidate" | "source";
  bbox: PdfCoordinates;
};

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
  const insetRadius = CANDIDATE_MARKER_RADIUS + CANDIDATE_MARKER_INSET;
  return Math.min(
    Math.max(value, insetRadius),
    Math.max(insetRadius, extent - insetRadius),
  );
}

function candidateMarkerOptions(
  bbox: PdfCoordinates,
  pageWidth: number,
  pageHeight: number,
): MarkerPoint[] {
  const [x0, y0, x1, y1] = bbox;
  const centerX = (x0 + x1) / 2;
  const centerY = (y0 + y1) / 2;
  const options: MarkerPoint[] = [];

  for (const ring of [0, 1]) {
    const offset = CANDIDATE_MARKER_RADIUS
      + CANDIDATE_MARKER_GAP
      + ring * (CANDIDATE_MARKER_RADIUS * 2 + CANDIDATE_MARKER_GAP * 2);
    options.push(
      { x: x1 + offset, y: y0 - offset },
      { x: x1 + offset, y: y1 + offset },
      { x: x0 - offset, y: y0 - offset },
      { x: x0 - offset, y: y1 + offset },
      { x: x1 + offset, y: centerY },
      { x: x0 - offset, y: centerY },
      { x: centerX, y: y0 - offset },
      { x: centerX, y: y1 + offset },
    );
  }

  const seen = new Set<string>();
  return options.flatMap((option) => {
    const point = {
      x: clampMarker(option.x, pageWidth),
      y: clampMarker(option.y, pageHeight),
    };
    const key = `${point.x}:${point.y}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [point];
  });
}

function markerOverlapsBox(point: MarkerPoint, bbox: PdfCoordinates): boolean {
  const [x0, y0, x1, y1] = bbox;
  const closestX = Math.min(Math.max(point.x, x0), x1);
  const closestY = Math.min(Math.max(point.y, y0), y1);
  return Math.hypot(point.x - closestX, point.y - closestY)
    < CANDIDATE_MARKER_RADIUS + CANDIDATE_MARKER_GAP;
}

function candidateLeaderTarget(
  point: MarkerPoint,
  bbox: PdfCoordinates,
): MarkerPoint {
  const [x0, y0, x1, y1] = bbox;
  const target = {
    x: Math.min(Math.max(point.x, x0), x1),
    y: Math.min(Math.max(point.y, y0), y1),
  };
  if (target.x !== point.x || target.y !== point.y) return target;

  const edges = [
    { distance: Math.abs(point.x - x0), point: { x: x0, y: point.y } },
    { distance: Math.abs(x1 - point.x), point: { x: x1, y: point.y } },
    { distance: Math.abs(point.y - y0), point: { x: point.x, y: y0 } },
    { distance: Math.abs(y1 - point.y), point: { x: point.x, y: y1 } },
  ];
  return edges.reduce((nearest, edge) => (
    edge.distance < nearest.distance ? edge : nearest
  )).point;
}

function chooseCandidateMarker(
  bbox: PdfCoordinates,
  pageWidth: number,
  pageHeight: number,
  obstacles: MarkerObstacle[],
  placedMarkers: MarkerPoint[],
): MarkerPoint {
  const options = candidateMarkerOptions(bbox, pageWidth, pageHeight);
  const preferred = options[0];
  return options.reduce((best, option, index) => {
    const markerOverlapCount = placedMarkers.filter((placed) => (
      Math.hypot(option.x - placed.x, option.y - placed.y)
        < CANDIDATE_MARKER_RADIUS * 2 + CANDIDATE_MARKER_GAP
    )).length;
    const boxOverlapCount = obstacles.filter((obstacle) => (
      markerOverlapsBox(option, obstacle.bbox)
    )).length;
    const distanceFromPreferred = preferred === undefined
      ? 0
      : Math.hypot(option.x - preferred.x, option.y - preferred.y);
    const leaderTarget = candidateLeaderTarget(option, bbox);
    const leaderDistance = Math.hypot(
      option.x - leaderTarget.x,
      option.y - leaderTarget.y,
    );
    const leaderShortfall = Math.max(
      0,
      CANDIDATE_MARKER_RADIUS + 5 - leaderDistance,
    );
    const score = markerOverlapCount * 1_000_000
      + boxOverlapCount * 500
      + leaderShortfall * 10_000
      + distanceFromPreferred * 10
      + index;
    return score < best.score ? { point: option, score } : best;
  }, {
    point: options[0] ?? {
      x: clampMarker(bbox[2], pageWidth),
      y: clampMarker(bbox[1], pageHeight),
    },
    score: Number.POSITIVE_INFINITY,
  }).point;
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
  const markerObstacles: MarkerObstacle[] = [
    ...candidates.map((item) => ({
      id: item.id,
      kind: "candidate" as const,
      bbox: transformBox(matrix, item.bbox),
    })),
    ...sources.map((item) => ({
      id: item.id,
      kind: "source" as const,
      bbox: transformBox(matrix, item.bbox),
    })),
  ];
  const placedCandidateMarkers: MarkerPoint[] = [];
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
    const bbox = transformBox(matrix, item.bbox);
    const marker = chooseCandidateMarker(
      bbox,
      pageWidth,
      pageHeight,
      markerObstacles.filter((obstacle) => (
        obstacle.kind !== "candidate" || obstacle.id !== item.id
      )),
      placedCandidateMarkers,
    );
    placedCandidateMarkers.push(marker);
    const leaderTarget = candidateLeaderTarget(marker, bbox);
    return [{
      item,
      itemId: item.itemId,
      candidateNumber: item.candidateNumber,
      markerX: marker.x,
      markerY: marker.y,
      leaderTargetX: leaderTarget.x,
      leaderTargetY: leaderTarget.y,
    }];
  });
  const selectedCandidateId = candidateMarkers.find(({ item, itemId }) =>
    selectedRelation({ itemId, itemIds: item.itemIds }, selected),
  )?.item.id;
  const activeBalloons = balloons.filter((item) => item.status !== "deleted");
  const selectedActiveBalloonId = activeBalloons.find((item) =>
    selectedBalloonId === item.id
    || selectedRelation({ itemId: item.itemId ?? item.id }, selected),
  )?.id;

  return (
    <svg
      aria-label={zhCN.pdf.overlay}
      data-scale={scale}
      width={pageWidth * scale}
      height={pageHeight * scale}
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      style={{ position: "absolute", inset: 0 }}
    >
      <defs aria-hidden="true">
        <marker
          id="candidate-arrowhead"
          viewBox="0 0 7 7"
          markerWidth={7}
          markerHeight={7}
          refX={6.5}
          refY={3.5}
          orient="auto"
          markerUnits="userSpaceOnUse"
        >
          <path d="M 0 0 L 7 3.5 L 0 7 z" fill="#111111" />
        </marker>
      </defs>
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
              className="pdf-overlay-candidate"
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
            className="pdf-overlay-source"
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
        leaderTargetX,
        leaderTargetY,
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
          <Fragment key={`candidate-number-${item.id}`}>
            <line
              className="pdf-overlay-candidate-leader"
              data-testid={`candidate-leader-${item.id}`}
              x1={markerX}
              y1={markerY}
              x2={leaderTargetX}
              y2={leaderTargetY}
              stroke="#111111"
              strokeWidth={1.1}
              markerEnd="url(#candidate-arrowhead)"
              vectorEffect="non-scaling-stroke"
              aria-hidden="true"
              style={{ pointerEvents: "none" }}
            />
            <g
              className="pdf-overlay-candidate-marker"
              data-testid={`candidate-number-${item.id}`}
              data-item-id={itemId}
              data-selected={isSelected}
              role="button"
              aria-label={zhCN.pdf.candidateMarker(candidateNumber)}
              tabIndex={
                selectItem === undefined
                  ? undefined
                  : item.id === (selectedCandidateId ?? candidateMarkers[0]?.item.id)
                    ? 0
                    : -1
              }
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
          </Fragment>
        );
      })}
      {activeBalloons.map((item) => {
        const [x, y] = transformPoint(matrix, item.center);
        const isSelected =
          selectedBalloonId === item.id
          || selectedRelation({ itemId: item.itemId ?? item.id }, selected);
        return (
          <BalloonMarker
            key={item.id}
            balloon={item}
            displayCenter={[x, y]}
            renderToPdfMatrix={effectiveRenderToPdfMatrix}
            selected={isSelected}
            readOnly={onMoveBalloon === undefined}
            tabIndex={
              item.id === (selectedActiveBalloonId ?? activeBalloons[0]?.id)
                ? 0
                : -1
            }
            onSelect={(itemId, balloonId) => {
              selectItem?.(itemId);
              onSelectBalloon?.(itemId, balloonId);
            }}
            onMove={onMoveBalloon}
          />
        );
      })}
    </svg>
  );
}
