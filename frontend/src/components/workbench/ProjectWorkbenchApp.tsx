import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getDocument } from "pdfjs-dist";

import { ApiError, getJson, postJson } from "../../api/client";
import type {
  BalloonOverlay,
  PdfDocumentLike,
  ProjectWorkbenchView,
  ProjectWorkbenchTransport,
  ReviewCommand,
  ReviewLockResponse,
} from "../../api/types";
import { applyBalloonCommand, generateBalloons } from "../../features/balloons/api";
import { BALLOON_RADIUS_PDF } from "../balloons/BalloonOverlay";
import {
  acquireReviewLock,
  confirmReviewedResult,
  freezeReviewItems,
  releaseReviewLock,
} from "../../features/review/api";
import { saveWorkingCopy } from "../../features/review/saveWorkingCopy";
import { apiErrorCopy, zhCN } from "../../copy/zhCN";
import {
  candidateMarkerNumber,
  deriveCandidateNumbers,
} from "./candidateNumbering";
import {
  isAutoAcceptedCandidateProjection,
} from "./inspectionItemPresentation";
import { InspectionWorkbench } from "./InspectionWorkbench";


const LOCK_RENEWAL_MS = 240_000;
const PREPARATION_NOT_READY_CODES = new Set([
  "coverage_blocking",
  "unresolved_confirmation",
  "balloon_required_unconfirmed",
]);

export type PdfLoader = (sourceUrl: string) => Promise<PdfDocumentLike>;


async function loadPdfDocument(sourceUrl: string): Promise<PdfDocumentLike> {
  const task = getDocument({ url: sourceUrl, withCredentials: false });
  return await task.promise as unknown as PdfDocumentLike;
}


type ProjectWorkbenchAppProps = {
  projectId: string;
  operatorId: string;
  loadPdf?: PdfLoader;
  onReset?: () => void;
};


export function ProjectWorkbenchApp({
  projectId,
  operatorId,
  loadPdf = loadPdfDocument,
  onReset,
}: ProjectWorkbenchAppProps) {
  const [snapshot, setSnapshot] = useState<ProjectWorkbenchView>();
  const [pdfDocument, setPdfDocument] = useState<PdfDocumentLike | null>(null);
  const [busy, setBusy] = useState(false);
  const [startupBlocked, setStartupBlocked] = useState(false);
  const [lockBlocked, setLockBlocked] = useState(false);
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState<string>();
  const [reviewedResultId, setReviewedResultId] = useState<string>();
  const snapshotRef = useRef<ProjectWorkbenchView | undefined>(undefined);
  const leaseExpiresAtRef = useRef<string | undefined>(undefined);
  const renewInFlightRef = useRef<Promise<ReviewLockResponse> | undefined>(undefined);
  const leavingRef = useRef(false);

  const safeError = (caught: unknown) => (
    caught instanceof ApiError ? apiErrorCopy(caught.code) : zhCN.errors.fallback
  );

  const refresh = useCallback(async () => {
    const transport = await getJson<ProjectWorkbenchTransport>(
      `/api/v1/projects/${projectId}/workbench`,
    );
    const loaded = transport as ProjectWorkbenchView;
    const controlledSource = `/api/v1/projects/${projectId}/source-pdf`;
    if (
      loaded.project.id !== projectId ||
      loaded.working_copy.project_id !== projectId ||
      loaded.source_pdf_url !== controlledSource
    ) {
      throw new Error("project workbench identity mismatch");
    }
    snapshotRef.current = loaded;
    setSnapshot(loaded);
    setReviewedResultId(loaded.reviewed_result_id ?? undefined);
    return loaded;
  }, [projectId]);

  const acquireLatestLease = useCallback(() => {
    const inFlight = renewInFlightRef.current;
    if (inFlight !== undefined) return inFlight;

    const pending = acquireReviewLock(postJson, projectId, operatorId).finally(() => {
      if (renewInFlightRef.current === pending) {
        renewInFlightRef.current = undefined;
      }
    });
    renewInFlightRef.current = pending;
    return pending;
  }, [operatorId, projectId]);

  const releaseLatestLease = useCallback(() => {
    if (leavingRef.current) return;
    leavingRef.current = true;

    const expiresAt = leaseExpiresAtRef.current;
    leaseExpiresAtRef.current = undefined;
    if (expiresAt !== undefined) {
      void releaseReviewLock(projectId, operatorId, expiresAt).catch(() => undefined);
    }

    const pending = renewInFlightRef.current;
    if (pending !== undefined) {
      void pending.then((lock) => {
        if (!leavingRef.current || lock.expires_at === expiresAt) return;
        return releaseReviewLock(
          projectId,
          operatorId,
          lock.expires_at,
        );
      }).catch(() => undefined);
    }
  }, [operatorId, projectId]);

  useEffect(() => {
    let cancelled = false;
    let renewal: number | undefined;
    leavingRef.current = false;

    const renew = async () => {
      if (leavingRef.current) return false;
      const lock = await acquireLatestLease();
      if (cancelled || leavingRef.current) return false;
      leaseExpiresAtRef.current = lock.expires_at;
      setLockBlocked(false);
      setError((current) => (
        current === zhCN.errors.lockRenewal ? undefined : current
      ));
      return true;
    };
    const start = async () => {
      try {
        if (!await renew()) return;
        const loaded = await refresh();
        const loadedPdf = await loadPdf(loaded.source_pdf_url);
        if (cancelled) return;
        setPdfDocument(loadedPdf);
        renewal = window.setInterval(() => {
          if (document.visibilityState === "hidden") return;
          void renew().catch(() => {
            setLockBlocked(true);
            setError(zhCN.errors.lockRenewal);
          });
        }, LOCK_RENEWAL_MS);
      } catch (caught) {
        if (!cancelled) {
          setStartupBlocked(true);
          setError(safeError(caught));
        }
      }
    };
    const onFocus = () => {
      if (leavingRef.current || document.visibilityState === "hidden") return;
      void renew().catch(() => {
        setLockBlocked(true);
        setError(zhCN.errors.lockRenewal);
      });
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") onFocus();
    };
    const onPageShow = () => {
      leavingRef.current = false;
      onFocus();
    };
    const onPageHide = () => releaseLatestLease();
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("pagehide", onPageHide);
    document.addEventListener("visibilitychange", onVisibilityChange);
    void start();
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("pagehide", onPageHide);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (renewal !== undefined) window.clearInterval(renewal);
    };
  }, [acquireLatestLease, loadPdf, refresh, releaseLatestLease]);

  const handleReset = onReset === undefined ? undefined : () => {
    releaseLatestLease();
    onReset();
  };

  const balloons = useMemo<BalloonOverlay[]>(
    () => snapshot?.balloons.map((balloon) => ({
      id: balloon.id,
      itemId: balloon.inspection_item_id,
      sourceId: balloon.source_location_id,
      pageIndex: balloon.page_index,
      center: balloon.center_pdf,
      number: balloon.formal_number ?? balloon.suggested_number,
      version: balloon.version,
      status: balloon.status,
      sortOrder: balloon.sort_order,
      anchor: balloon.anchor_bbox_pdf,
      leaderTarget: balloon.leader_target_pdf,
      placementStatus: balloon.placement_status,
      collisionFlags: balloon.collision_flags,
      radius: BALLOON_RADIUS_PDF,
    })) ?? [],
    [snapshot],
  );
  const candidateNumbers = useMemo(
    () => deriveCandidateNumbers(snapshot?.working_copy.items ?? []),
    [snapshot?.working_copy.items],
  );
  const run = async (
    nextStatus: string,
    action: () => Promise<unknown>,
    completedStatus = zhCN.workbench.completed(nextStatus),
  ): Promise<boolean> => {
    if (busy || startupBlocked || lockBlocked || snapshot === undefined) return false;
    setBusy(true);
    setError(undefined);
    setStatus(nextStatus);
    try {
      await action();
      await refresh();
      setStatus(completedStatus);
      return true;
    } catch (caught) {
      setError(safeError(caught));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const save = async (command: ReviewCommand) => {
    const saved = await run(
      zhCN.workbench.saving,
      async () => {
        const currentSnapshot = snapshotRef.current;
        if (currentSnapshot === undefined) {
          throw new Error("project workbench is not loaded");
        }
        await saveWorkingCopy(
          postJson,
          projectId,
          operatorId,
          currentSnapshot.working_copy.version,
          command,
        );
      },
      zhCN.workbench.actionSubmitted,
    );
    if (!saved) throw new Error("working copy save failed");
  };

  const balloonCommand = async (
    nextStatus: string,
    command: Parameters<typeof applyBalloonCommand>[3],
  ) => run(nextStatus, () => applyBalloonCommand(
    postJson,
    projectId,
    operatorId,
    command,
  ));
  const prepareReview = async (): Promise<void> => {
    if (busy || startupBlocked || lockBlocked || snapshot === undefined) return;
    setBusy(true);
    setError(undefined);
    setStatus(zhCN.balloon.generate);
    try {
      if (snapshot.working_copy.items_frozen_at == null) {
        await freezeReviewItems(
          postJson,
          projectId,
          operatorId,
          snapshot.working_copy.version,
        );
      }
      if (snapshot.balloons.every((balloon) => balloon.status === "deleted")) {
        await generateBalloons(
          postJson,
          projectId,
          operatorId,
          snapshot.working_copy.version,
        );
      }
      await refresh();
      setStatus(zhCN.workbench.balloonsGenerated);
    } catch (caught) {
      if (
        caught instanceof ApiError
        && PREPARATION_NOT_READY_CODES.has(caught.code)
      ) {
        setStatus(undefined);
        return;
      }
      setError(safeError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const confirmReviewForExport = async (): Promise<string> => {
    if (reviewedResultId !== undefined) return reviewedResultId;
    let nextReviewedResultId: string | undefined;
    const confirmed = await run(
      zhCN.balloon.confirm,
      async () => {
        if (snapshot === undefined) {
          throw new Error("project workbench is not loaded");
        }
        const reviewed = await confirmReviewedResult(
          postJson,
          projectId,
          operatorId,
          snapshot.working_copy.version,
        );
        nextReviewedResultId = reviewed.id;
        setReviewedResultId(reviewed.id);
      },
      zhCN.workbench.reviewedConfirmed,
    );
    if (!confirmed || nextReviewedResultId === undefined) {
      throw new Error("review confirmation failed");
    }
    return nextReviewedResultId;
  };

  if (error !== undefined && snapshot === undefined) {
    return (
      <main className="workbench-shell">
        <p role="alert">{error}</p>
        {handleReset === undefined ? null : (
          <button
            type="button"
            className="workbench-reset-action"
            onClick={handleReset}
          >
            {zhCN.workbench.returnToDrawingList}
          </button>
        )}
      </main>
    );
  }
  if (snapshot === undefined) {
    return (
      <main className="workbench-shell" aria-busy="true">
        {zhCN.workbench.loading}
      </main>
    );
  }

  return (
    <>
      {error === undefined ? null : <p role="alert">{error}</p>}
      <InspectionWorkbench
        pdfDocument={pdfDocument}
        pageCount={snapshot.pages.length}
        candidates={snapshot.candidates.map((candidate) => {
          const item = snapshot.working_copy.items.find(
            (entry) => entry.item_id === candidate.item_id,
          );
          const candidateNumber = candidateNumbers.get(candidate.item_id);
          return {
            id: candidate.id,
            itemId: candidate.item_id,
            pageIndex: candidate.page_index,
            bbox: candidate.bbox_pdf,
            candidateNumber,
            confidenceBand: candidate.confidence_band,
            reviewDisposition: candidate.review_disposition,
            status: candidate.status,
            autoAccepted: item !== undefined
              && isAutoAcceptedCandidateProjection(item, candidate),
            showCandidateMarker: candidateMarkerNumber(
              item ?? {},
              candidateNumber,
            ) !== undefined,
          };
        })}
        sources={snapshot.sources.map((source) => ({
          id: source.id,
          itemIds: source.item_ids,
          pageIndex: source.page_index,
          bbox: source.bbox_pdf,
          rawText: source.raw_text,
        }))}
        balloons={balloons}
        pageTransforms={snapshot.pages.map((page) => ({
          pageIndex: page.page_index,
          pdfToRenderMatrix: page.pdf_to_render_matrix,
          renderToPdfMatrix: page.render_to_pdf_matrix,
        }))}
        items={snapshot.working_copy.items}
        sipMetadataSuggestions={snapshot.sip_metadata_suggestions}
        workingCopy={snapshot.working_copy}
        balloonBlockers={snapshot.balloon_blockers}
        projectState={snapshot.project.state}
        projectId={projectId}
        reviewedResultId={reviewedResultId}
        initialExport={snapshot.latest_export}
        exportPost={postJson}
        operatorId={operatorId}
        actionState={status}
        busy={busy || startupBlocked || lockBlocked}
        onReset={handleReset}
        onSave={save}
        onPrepareReview={prepareReview}
        onConfirmReview={confirmReviewForExport}
        onMoveBalloon={(balloonId, expectedVersion, centerPdf) => void balloonCommand(
          zhCN.workbench.movingBalloon,
          {
            type: "move",
            balloon_id: balloonId,
            expected_version: expectedVersion,
            center_pdf: centerPdf,
          },
        )}
        onDeleteBalloon={(balloonId, expectedVersion) => void balloonCommand(
          zhCN.workbench.deletingBalloon,
          { type: "delete", balloon_id: balloonId, expected_version: expectedVersion },
        )}
        onRebuildBalloon={(balloonId, expectedVersion) => void balloonCommand(
          zhCN.workbench.rebuildingBalloon,
          { type: "rebuild", balloon_id: balloonId, expected_version: expectedVersion },
        )}
        onReorderBalloon={(balloonId, expectedVersion, sortOrder) => void balloonCommand(
          zhCN.workbench.reorderingBalloon,
          {
            type: "reorder",
            balloon_id: balloonId,
            expected_version: expectedVersion,
            sort_order: sortOrder,
          },
        )}
        onRenumberBalloons={(orderedIds, expectedVersions) => void balloonCommand(
          zhCN.workbench.renumberingBalloons,
          {
            type: "renumber",
            ordered_balloon_ids: orderedIds,
            expected_versions: expectedVersions,
          },
        )}
      />
    </>
  );
}
