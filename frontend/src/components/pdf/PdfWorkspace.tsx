import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { GlobalWorkerOptions } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import type {
  BalloonOverlay,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  PdfRenderTaskLike,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
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
  onPageChange?: (pageIndex: number) => void;
  auxiliaryPanel?: ReactNode;
};

function PdfThumbnail({
  pdfDocument,
  pageIndex,
}: {
  pdfDocument: PdfDocumentLike | null;
  pageIndex: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    setAvailable(false);
    if (pdfDocument === null) return;
    let cancelled = false;
    let renderTask: PdfRenderTaskLike | undefined;

    void (async () => {
      try {
        const page = await pdfDocument.getPage(pageIndex + 1);
        const base = page.getViewport({ scale: 1 });
        const thumbnailScale = Math.min(48 / base.width, 52 / base.height);
        const viewport = page.getViewport({ scale: thumbnailScale });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (cancelled || canvas === null || context == null) return;
        canvas.width = Math.max(1, Math.round(viewport.width));
        canvas.height = Math.max(1, Math.round(viewport.height));
        renderTask = page.render({ canvasContext: context, viewport });
        await renderTask.promise;
        if (!cancelled) setAvailable(true);
      } catch (error) {
        if (
          !cancelled
          && !(error instanceof Error
            && error.name === "RenderingCancelledException")
        ) {
          setAvailable(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pageIndex, pdfDocument]);

  return (
    <>
      <canvas
        ref={canvasRef}
        data-testid={`pdf-thumbnail-${pageIndex + 1}`}
        hidden={!available}
        aria-hidden="true"
      />
      {available ? null : (
        <span>{zhCN.pdf.thumbnailUnavailable(pageIndex + 1)}</span>
      )}
    </>
  );
}


export function PdfWorkspace({
  pdfDocument,
  candidates,
  sources,
  balloons,
  pageTransforms = DEFAULT_PAGE_TRANSFORMS,
  pageCount = 1,
  fallbackPageSize = DEFAULT_PAGE_SIZE,
  selectedItemId,
  selectedSourceId,
  selectedBalloonId,
  onSelectItem,
  onSelectSource,
  onSelectBalloon,
  onMoveBalloon,
  onPageChange,
  auxiliaryPanel,
}: PdfWorkspaceProps) {
  const workspaceRef = useRef<HTMLElement>(null);
  const scrollFrameRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const locatedSelectionRef = useRef<string | undefined>(undefined);
  const [pageIndex, setPageIndex] = useState(0);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [expanded, setExpanded] = useState(false);
  const [auxiliaryOpen, setAuxiliaryOpen] = useState(false);
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
    if (selectedSourceId === undefined) return;
    const sourcePage = sources.find(
      (source) => source.id === selectedSourceId,
    )?.pageIndex;
    if (sourcePage !== undefined && sourcePage !== pageIndex) {
      setPageIndex(sourcePage);
    }
  }, [pageIndex, selectedSourceId, sources]);

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
        setRenderError(zhCN.pdf.renderFailed);
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
      aria-label={zhCN.pdf.workspace}
      aria-busy={pdfDocument === null}
      data-testid="pdf-workspace"
      data-selected-id={selection ?? ""}
      data-expanded={expanded}
      className="pdf-workspace"
    >
      <div
        aria-label={zhCN.pdf.controls}
        className="pdf-controls"
      >
        <button
          type="button"
          aria-label={zhCN.pdf.previous}
          disabled={pageIndex === 0}
          onClick={() => setPageIndex((current) => Math.max(0, current - 1))}
        >
          {zhCN.pdf.previous}
        </button>
        <span className="pdf-control-status" data-testid="page-indicator">
          {pageIndex + 1} / {totalPages}
        </span>
        <button
          type="button"
          aria-label={zhCN.pdf.next}
          disabled={pageIndex >= totalPages - 1}
          onClick={() => setPageIndex((current) => Math.min(totalPages - 1, current + 1))}
        >
          {zhCN.pdf.next}
        </button>
        <button
          type="button"
          aria-label={zhCN.pdf.zoomOut}
          onClick={() => setScale((current) => Math.max(0.5, current - 0.25))}
        >
          {zhCN.pdf.zoomOut}
        </button>
        <output className="pdf-control-status" aria-label={zhCN.pdf.zoomLevel}>
          {Math.round(scale * 100)}%
        </output>
        <button
          type="button"
          aria-label={zhCN.pdf.zoomIn}
          onClick={() => setScale((current) => Math.min(4, current + 0.25))}
        >
          {zhCN.pdf.zoomIn}
        </button>
        <button type="button" aria-label={zhCN.pdf.panLeft} onClick={() => setPan((p) => ({ ...p, x: p.x - 24 }))}>
          {zhCN.pdf.panLeft}
        </button>
        <button type="button" aria-label={zhCN.pdf.panRight} onClick={() => setPan((p) => ({ ...p, x: p.x + 24 }))}>
          {zhCN.pdf.panRight}
        </button>
        <button type="button" aria-label={zhCN.pdf.panUp} onClick={() => setPan((p) => ({ ...p, y: p.y - 24 }))}>
          {zhCN.pdf.panUp}
        </button>
        <button type="button" aria-label={zhCN.pdf.panDown} onClick={() => setPan((p) => ({ ...p, y: p.y + 24 }))}>
          {zhCN.pdf.panDown}
        </button>
        <button
          type="button"
          aria-label={zhCN.pdf.fit}
          onClick={() => {
            const frame = scrollFrameRef.current;
            if (
              frame === null
              || frame.clientWidth <= 24
              || frame.clientHeight <= 24
              || pageSize.width <= 0
              || pageSize.height <= 0
            ) return;
            const fitted = Math.min(
              (frame.clientWidth - 24) / pageSize.width,
              (frame.clientHeight - 24) / pageSize.height,
            );
            setScale(Math.min(4, Math.max(0.1, fitted)));
            setPan({ x: 0, y: 0 });
          }}
        >
          {zhCN.pdf.fit}
        </button>
        {auxiliaryPanel === undefined ? null : (
          <button
            type="button"
            aria-controls="pdf-auxiliary-panel"
            aria-expanded={auxiliaryOpen}
            onClick={() => setAuxiliaryOpen((current) => !current)}
          >
            {auxiliaryOpen
              ? zhCN.pdf.collapseAuxiliary
              : zhCN.pdf.expandAuxiliary}
          </button>
        )}
        <button
          type="button"
          aria-label={expanded ? zhCN.pdf.collapse : zhCN.pdf.expand}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? zhCN.pdf.collapse : zhCN.pdf.expand}
        </button>
      </div>
      {auxiliaryPanel === undefined ? null : (
        <div
          id="pdf-auxiliary-panel"
          className="pdf-auxiliary-panel"
          hidden={!auxiliaryOpen}
        >
          {auxiliaryPanel}
        </div>
      )}
      {renderError === undefined ? null : <p role="alert">{renderError}</p>}
      <div className="pdf-content">
        <nav className="pdf-thumbnails" aria-label={zhCN.pdf.pages}>
          {Array.from({ length: totalPages }, (_, index) => (
            <button
              key={index}
              type="button"
              aria-label={zhCN.pdf.viewPage(index + 1)}
              aria-current={pageIndex === index ? "page" : undefined}
              onClick={() => setPageIndex(index)}
            >
              <PdfThumbnail pdfDocument={pdfDocument} pageIndex={index} />
              <small>{zhCN.inspection.sourcePage(index + 1)}</small>
            </button>
          ))}
        </nav>
        <div
          ref={scrollFrameRef}
          className="pdf-scroll-frame"
          data-testid="pdf-scroll-frame"
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
              selectedSourceId={selectedSourceId}
              selectedBalloonId={selectedBalloonId}
              onSelectItem={(itemId) => {
                setLocalSelectedItemId(itemId);
                onSelectItem?.(itemId);
              }}
              onSelectSource={onSelectSource}
              onSelectBalloon={onSelectBalloon}
              onMoveBalloon={onMoveBalloon}
            />
          </div>
        </div>
      </div>
      <ul className="drawing-legend" aria-label={zhCN.pdf.legend}>
        <li><i data-color="balloon" />{zhCN.pdf.formalBalloon}</li>
        <li><i data-color="candidate" />{zhCN.pdf.candidate}</li>
        <li><i data-color="source" />{zhCN.pdf.source}</li>
        <li><i data-color="excluded" />{zhCN.pdf.excluded}</li>
      </ul>
    </section>
  );
}
