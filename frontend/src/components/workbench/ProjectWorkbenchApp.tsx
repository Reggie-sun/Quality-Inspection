import { useCallback, useEffect, useMemo, useState } from "react";
import { getDocument } from "pdfjs-dist";

import { ApiError, getJson, postJson } from "../../api/client";
import type {
  BalloonOverlay,
  PdfDocumentLike,
  ProjectWorkbenchResponse,
  ReviewCommand,
} from "../../api/types";
import { applyBalloonCommand, generateBalloons } from "../../features/balloons/api";
import { BALLOON_RADIUS_PDF } from "../balloons/BalloonOverlay";
import {
  acquireReviewLock,
  confirmReviewedResult,
  freezeReviewItems,
} from "../../features/review/api";
import { saveWorkingCopy } from "../../features/review/saveWorkingCopy";
import { apiErrorCopy, zhCN } from "../../copy/zhCN";
import { InspectionWorkbench } from "./InspectionWorkbench";


const LOCK_RENEWAL_MS = 240_000;

export type PdfLoader = (sourceUrl: string) => Promise<PdfDocumentLike>;


async function loadPdfDocument(sourceUrl: string): Promise<PdfDocumentLike> {
  const task = getDocument({ url: sourceUrl, withCredentials: false });
  return await task.promise as unknown as PdfDocumentLike;
}


type ProjectWorkbenchAppProps = {
  projectId: string;
  operatorId: string;
  loadPdf?: PdfLoader;
};


export function ProjectWorkbenchApp({
  projectId,
  operatorId,
  loadPdf = loadPdfDocument,
}: ProjectWorkbenchAppProps) {
  const [snapshot, setSnapshot] = useState<ProjectWorkbenchResponse>();
  const [pdfDocument, setPdfDocument] = useState<PdfDocumentLike | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string>();
  const [error, setError] = useState<string>();
  const [reviewedResultId, setReviewedResultId] = useState<string>();

  const safeError = (caught: unknown) => (
    caught instanceof ApiError ? apiErrorCopy(caught.code) : zhCN.errors.fallback
  );

  const refresh = useCallback(async () => {
    const loaded = await getJson<ProjectWorkbenchResponse>(
      `/api/v1/projects/${projectId}/workbench`,
    );
    const controlledSource = `/api/v1/projects/${projectId}/source-pdf`;
    if (
      loaded.project.id !== projectId ||
      loaded.working_copy.project_id !== projectId ||
      loaded.source_pdf_url !== controlledSource
    ) {
      throw new Error("project workbench identity mismatch");
    }
    setSnapshot(loaded);
    setReviewedResultId(loaded.reviewed_result_id ?? undefined);
    return loaded;
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    let renewal: number | undefined;

    const renew = async () => {
      await acquireReviewLock(postJson, projectId, operatorId);
    };
    const start = async () => {
      try {
        await renew();
        const loaded = await refresh();
        const document = await loadPdf(loaded.source_pdf_url);
        if (cancelled) return;
        setPdfDocument(document);
        renewal = window.setInterval(() => {
          void renew().catch(() => {
            setError(zhCN.errors.lockRenewal);
          });
        }, LOCK_RENEWAL_MS);
      } catch (caught) {
        if (!cancelled) {
          setError(safeError(caught));
        }
      }
    };
    const onFocus = () => {
      void renew().catch(() => {
        setError(zhCN.errors.lockRenewal);
      });
    };
    window.addEventListener("focus", onFocus);
    void start();
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      if (renewal !== undefined) window.clearInterval(renewal);
    };
  }, [loadPdf, operatorId, projectId, refresh]);

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

  const run = async (
    nextStatus: string,
    action: () => Promise<unknown>,
    completedStatus = zhCN.workbench.completed(nextStatus),
  ): Promise<boolean> => {
    if (busy || snapshot === undefined) return false;
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
        if (snapshot === undefined) throw new Error("project workbench is not loaded");
        await saveWorkingCopy(
          postJson,
          projectId,
          operatorId,
          snapshot.working_copy.version,
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

  if (error !== undefined && snapshot === undefined) {
    return <main role="alert">{error}</main>;
  }
  if (snapshot === undefined) {
    return <main aria-busy="true">{zhCN.workbench.loading}</main>;
  }

  return (
    <>
      {error === undefined ? null : <p role="alert">{error}</p>}
      <InspectionWorkbench
        pdfDocument={pdfDocument}
        pageCount={snapshot.pages.length}
        candidates={snapshot.candidates.map((candidate) => ({
          id: candidate.id,
          itemId: candidate.item_id,
          pageIndex: candidate.page_index,
          bbox: candidate.bbox_pdf,
        }))}
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
        workingCopy={snapshot.working_copy}
        balloonBlockers={snapshot.balloon_blockers}
        projectState={snapshot.project.state}
        projectId={projectId}
        reviewedResultId={reviewedResultId}
        initialExport={snapshot.latest_export}
        exportPost={postJson}
        operatorId={operatorId}
        actionState={status}
        busy={busy || error !== undefined}
        onSave={save}
        onFreeze={() => void run(
          zhCN.balloon.freeze,
          () => freezeReviewItems(
            postJson,
            projectId,
            operatorId,
            snapshot.working_copy.version,
          ),
          zhCN.workbench.itemsFrozen,
        )}
        onGenerate={() => void run(
          zhCN.balloon.generate,
          () => generateBalloons(
            postJson,
            projectId,
            operatorId,
            snapshot.working_copy.version,
          ),
          zhCN.workbench.balloonsGenerated,
        )}
        onConfirm={() => void run(
          zhCN.balloon.confirm,
          async () => {
            const reviewed = await confirmReviewedResult(
              postJson,
              projectId,
              operatorId,
              snapshot.working_copy.version,
            );
            setReviewedResultId(reviewed.id);
          },
          zhCN.workbench.reviewedConfirmed,
        )}
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
