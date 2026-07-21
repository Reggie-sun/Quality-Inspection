import type {
  BalloonOverlay,
  OverlayBox,
  PdfCoordinates,
  PdfMatrix,
} from "../../api/types";


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
  selectedId,
  onSelect,
}: OverlayLayerProps) {
  const matrix = normalizeMatrix(pdfToRenderMatrix);

  return (
    <svg
      aria-label="engineering overlays"
      data-scale={scale}
      width={pageWidth * scale}
      height={pageHeight * scale}
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      style={{ position: "absolute", inset: 0 }}
    >
      {candidates.map((item) => {
        const [x0, y0, x1, y1] = transformBox(matrix, item.bbox);
        return (
          <rect
            key={item.id}
            data-testid={`candidate-${item.id}`}
            data-selected={selectedId === item.id}
            x={x0}
            y={y0}
            width={x1 - x0}
            height={y1 - y0}
            fill="transparent"
            stroke={selectedId === item.id ? "#dc2626" : "#f59e0b"}
            strokeWidth={selectedId === item.id ? 3 : 1.5}
            onClick={() => onSelect?.(item.id)}
            style={{ cursor: onSelect ? "pointer" : "default" }}
          />
        );
      })}
      {sources.map((item) => {
        const [x0, y0, x1, y1] = transformBox(matrix, item.bbox);
        return (
          <rect
            key={item.id}
            data-testid={`source-${item.id}`}
            x={x0}
            y={y0}
            width={x1 - x0}
            height={y1 - y0}
            fill="transparent"
            stroke="#2563eb"
            strokeDasharray="4 3"
            strokeWidth={1.5}
            style={{ pointerEvents: "none" }}
          />
        );
      })}
      {balloons.map((item) => {
        const [x, y] = transformPoint(matrix, item.center);
        return (
          <g
            key={item.id}
            data-testid={`balloon-${item.id}`}
            style={{ pointerEvents: "none" }}
          >
            <circle
              cx={x}
              cy={y}
              r={10}
              fill="white"
              stroke="#dc2626"
              strokeWidth={1.5}
            />
            <text
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={10}
            >
              {item.number}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
