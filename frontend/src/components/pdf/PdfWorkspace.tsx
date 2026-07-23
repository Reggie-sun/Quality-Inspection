import { useEffect, useMemo, useRef, useState } from "react";
import { GlobalWorkerOptions } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type {
  BalloonOverlay,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  PdfRenderTaskLike,
} from "../../api/types";
import { OverlayLayer } from "./OverlayLayer";
import { relatedItemIds } from "../workbench/selection";


GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const DEFAULT_PAGE_SIZE: [number, number] = [720, 480];
const DEFAULT_PAGE_TRANSFORMS: PdfPageTransform[] = [];

type PdfWorkspaceProps = {
  pdfDocument: PdfDocumentLike | null;
  candidates: OverlayBox[];
  sources: OverlayBox[];
  balloons: BalloonOverlay[];
  pageTransforms?: PdfPageTransform[];
  pageCount?: number;
  fallbackPageSize?: [number, number];
  selectedItemId?: string;
  selectedBalloonId?: string;
  onSelectItem?: (itemId: string) => void;
  onSelectBalloon?: (itemId: string, balloonId: string) => void;
  onMoveBalloon?: (
    balloonId: string,
    expectedVersion: number,
    centerPdf: [number, number],
  ) => void;
  onPageChange?: (pageIndex: number) => void;
};


export function PdfWorkspace({
  pdfDocument,
  candidates,
  sources,
  balloons,
  pageTransforms = DEFAULT_PAGE_TRANSFORMS,
  pageCount = 1,
  fallbackPageSize = DEFAULT_PAGE_SIZE,
  selectedItemId,
  selectedBalloonId,
  onSelectItem,
  onSelectBalloon,
  onMoveBalloon,
  onPageChange,
}: PdfWorkspaceProps) {
  const workspaceRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const locatedSelectionRef = useRef<string | undefined>(undefined);
  const [pageIndex, setPageIndex] = useState(0);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [localSelectedItemId, setLocalSelectedItemId] = useState<string>();
  const [renderError, setRenderError] = useState<string>();
  const [pageSize, setPageSize] = useState({
    width: fallbackPageSize[0],
    height: fallbackPageSize[1],
  });
  const totalPages = pdfDocument?.numPages ?? pageCount;
  const selection = selectedItemId ?? localSelectedItemId;
  const currentPageTransform = useMemo(
    () => pageTransforms.find((transform) => transform.pageIndex === pageIndex),
    [pageIndex, pageTransforms],
  );

  useEffect(() => {
    onPageChange?.(pageIndex);
  }, [onPageChange, pageIndex]);

  useEffect(() => {
    if (selection === undefined) {
      locatedSelectionRef.current = undefined;
      return;
    }
    const related = [
      ...candidates.filter((item) => relatedItemIds({
        itemId: item.itemId ?? item.id,
        itemIds: item.itemIds,
      }).includes(selection)),
      ...sources.filter((item) => relatedItemIds(item).includes(selection)),
      ...balloons.filter((item) => (item.itemId ?? item.id) === selection),
    ];
    const targetPage = related.find((item) => item.pageIndex !== undefined)?.pageIndex;
    const isNewSelection = locatedSelectionRef.current !== selection;
    locatedSelectionRef.current = selection;
    if (isNewSelection && targetPage !== undefined && targetPage !== pageIndex) {
      setPageIndex(targetPage);
      return;
    }
    const selectedOverlay = workspaceRef.current
      ?.querySelector<SVGElement>("[data-selected='true']");
    selectedOverlay?.scrollIntoView?.({ block: "center", inline: "center" });
  }, [balloons, candidates, pageIndex, selection, sources]);

  useEffect(() => {
    setRenderError(undefined);
    if (pdfDocument === null) {
      setPageSize({ width: fallbackPageSize[0], height: fallbackPageSize[1] });
      return;
    }
    let cancelled = false;
    let renderTask: PdfRenderTaskLike | undefined;

    const renderPage = async () => {
      try {
        const page = await pdfDocument.getPage(pageIndex + 1);
        if (cancelled) return;
        const unscaledViewport = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale });
        setPageSize({
          width: unscaledViewport.width,
          height: unscaledViewport.height,
        });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (
          canvas === null ||
          canvas === undefined ||
          context === null ||
          context === undefined
        ) return;
        canvas.width = Math.round(viewport.width);
        canvas.height = Math.round(viewport.height);
        renderTask = page.render({ canvasContext: context, viewport });
        await renderTask.promise;
      } catch (error) {
        if (
          cancelled ||
          (error instanceof Error && error.name === "RenderingCancelledException")
        ) return;
        setRenderError("PDF page could not be rendered");
      }
    };

    void renderPage();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [fallbackPageSize, pageIndex, pdfDocument, scale]);

  const pageCandidates = useMemo(
    () => candidates.filter((item) => (item.pageIndex ?? pageIndex) === pageIndex),
    [candidates, pageIndex],
  );
  const pageSources = useMemo(
    () => sources.filter((item) => (item.pageIndex ?? pageIndex) === pageIndex),
    [pageIndex, sources],
  );
  const pageBalloons = useMemo(
    () => balloons.filter(
      (item) =>
        item.status !== "deleted" &&
        (item.pageIndex ?? pageIndex) === pageIndex,
    ),
    [balloons, pageIndex],
  );

  return (
    <section
      ref={workspaceRef}
      aria-label="PDF review workspace"
      data-testid="pdf-workspace"
      data-selected-id={selection ?? ""}
      style={{
        padding: 14,
        background: "white",
        border: "1px solid #e2e8f0",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <div
        aria-label="PDF controls"
        style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}
      >
        <button
          type="button"
          aria-label="Previous page"
          disabled={pageIndex === 0}
          onClick={() => setPageIndex((current) => Math.max(0, current - 1))}
        >
          Previous
        </button>
        <span data-testid="page-indicator">
          {pageIndex + 1} / {totalPages}
        </span>
        <button
          type="button"
          aria-label="Next page"
          disabled={pageIndex >= totalPages - 1}
          onClick={() => setPageIndex((current) => Math.min(totalPages - 1, current + 1))}
        >
          Next
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={() => setScale((current) => Math.max(0.5, current - 0.25))}
        >
          Zoom out
        </button>
        <output aria-label="Zoom level">{Math.round(scale * 100)}%</output>
        <button
          type="button"
          aria-label="Zoom in"
          onClick={() => setScale((current) => Math.min(4, current + 0.25))}
        >
          Zoom in
        </button>
        <button type="button" aria-label="Pan left" onClick={() => setPan((p) => ({ ...p, x: p.x - 24 }))}>
          Pan left
        </button>
        <button type="button" aria-label="Pan right" onClick={() => setPan((p) => ({ ...p, x: p.x + 24 }))}>
          Pan right
        </button>
        <button type="button" aria-label="Pan up" onClick={() => setPan((p) => ({ ...p, y: p.y - 24 }))}>
          Pan up
        </button>
        <button type="button" aria-label="Pan down" onClick={() => setPan((p) => ({ ...p, y: p.y + 24 }))}>
          Pan down
        </button>
      </div>
      {renderError === undefined ? null : <p role="alert">{renderError}</p>}
      <div
        style={{
          overflow: "auto",
          minHeight: 520,
          maxHeight: "calc(100vh - 285px)",
          border: "1px solid #cbd5e1",
          borderRadius: 8,
          background: "#e9edf3",
        }}
      >
        <div
          data-testid="pdf-page-layer"
          style={{
            position: "relative",
            width: pageSize.width * scale,
            height: pageSize.height * scale,
            transform: `translate(${pan.x}px, ${pan.y}px)`,
            transformOrigin: "top left",
            background: "white",
          }}
        >
          <canvas
            ref={canvasRef}
            data-testid="pdf-canvas"
            width={Math.round(pageSize.width * scale)}
            height={Math.round(pageSize.height * scale)}
          />
          <OverlayLayer
            pageWidth={pageSize.width}
            pageHeight={pageSize.height}
            scale={scale}
            candidates={pageCandidates}
            sources={pageSources}
            balloons={pageBalloons}
            pdfToRenderMatrix={currentPageTransform?.pdfToRenderMatrix}
            renderToPdfMatrix={currentPageTransform?.renderToPdfMatrix}
            selectedItemId={selection}
            selectedBalloonId={selectedBalloonId}
            onSelectItem={(itemId) => {
              setLocalSelectedItemId(itemId);
              onSelectItem?.(itemId);
            }}
            onSelectBalloon={onSelectBalloon}
            onMoveBalloon={onMoveBalloon}
          />
        </div>
      </div>
    </section>
  );
}
