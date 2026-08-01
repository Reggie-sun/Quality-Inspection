import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import type { ExportArtifactKind, ExportJob, PostJson } from "../../api/types";
import { apiErrorCopy, zhCN } from "../../copy/zhCN";
import { createExport, exportDownloadPath } from "../../features/exports/api";


type ExportPanelProps = {
  projectId: string;
  reviewedResultId?: string;
  canFinalize?: boolean;
  sipPendingCount?: number;
  sipExceptionCount?: number;
  projectMetadataConfirmed?: boolean;
  missingProjectMetadataFields?: string[];
  projectMetadataBlocker?: "conflict" | "save_failed" | "ready_to_save" | "auto_saving";
  balloonBlockers: string[];
  post: PostJson;
  initialExport?: ExportJob | null;
  onConfirmReview?: () => Promise<string>;
};

const DOWNLOADS: Array<{ kind: ExportArtifactKind; label: string }> = [
  {
    kind: "ballooned_pdf",
    label: zhCN.export.downloads.ballooned_pdf,
  },
  {
    kind: "sip_excel",
    label: zhCN.export.downloads.sip_excel,
  },
  {
    kind: "manifest",
    label: zhCN.export.downloads.manifest,
  },
];


export function ExportPanel({
  projectId,
  reviewedResultId,
  canFinalize = false,
  sipPendingCount = 0,
  sipExceptionCount = 0,
  projectMetadataConfirmed = true,
  missingProjectMetadataFields = [],
  projectMetadataBlocker,
  balloonBlockers,
  post,
  initialExport,
  onConfirmReview,
}: ExportPanelProps) {
  const [exportJob, setExportJob] = useState<ExportJob | undefined>(
    initialExport ?? undefined,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    setExportJob(initialExport ?? undefined);
    setError(undefined);
  }, [initialExport]);

  const canExport =
    balloonBlockers.length === 0
    && (
      reviewedResultId !== undefined
      || (canFinalize && onConfirmReview !== undefined)
    );
  const exportInFlight = busy
    || exportJob?.status === "running";
  const downloadableKinds = new Set(
    exportJob?.artifacts
      .filter((artifact) => artifact.downloadable)
      .map((artifact) => artifact.kind) ?? [],
  );
  const atomicSuccess = exportJob?.status === "success"
    && DOWNLOADS.every(({ kind }) => downloadableKinds.has(kind))
    && downloadableKinds.size === DOWNLOADS.length;
  const status = reviewedResultId === undefined && sipExceptionCount > 0
    ? zhCN.export.sipExceptions(sipExceptionCount)
    : reviewedResultId === undefined && sipPendingCount > 0
      ? zhCN.export.sipPending(sipPendingCount)
    : reviewedResultId === undefined && !projectMetadataConfirmed
      ? missingProjectMetadataFields.length > 0
        ? zhCN.export.missingProjectSip(missingProjectMetadataFields)
        : projectMetadataBlocker !== undefined
          ? zhCN.export.projectSipBlockers[projectMetadataBlocker]
        : zhCN.export.pendingProjectSip
      : reviewedResultId === undefined && !canFinalize
        ? zhCN.export.notReviewed
    : balloonBlockers.length > 0
      ? zhCN.export.blocked
      : exportInFlight
        ? zhCN.export.running
        : exportJob?.status === "failed" || error !== undefined
          ? zhCN.export.failed
          : atomicSuccess
            ? zhCN.export.available
            : zhCN.export.ready;

  return (
    <section className="export-panel" aria-label={zhCN.export.region}>
      <div className="panel-heading">
        <div>
          <h2>{zhCN.export.title}</h2>
          <p>{zhCN.export.atomicHint}</p>
        </div>
        <span
          className="status-badge"
          data-status={status}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {status}
        </span>
      </div>
      <button
        type="button"
        className="primary-action"
        disabled={!canExport || exportInFlight}
        onClick={() => {
          if (!canExport || exportInFlight) return;
          setBusy(true);
          setError(undefined);
          setExportJob(undefined);
          const reviewed = reviewedResultId !== undefined
            ? Promise.resolve(reviewedResultId)
            : onConfirmReview?.();
          if (reviewed === undefined) {
            setBusy(false);
            return;
          }
          void reviewed
            .then((resultId) => createExport(post, projectId, resultId))
            .then(setExportJob)
            .catch((caught) => {
              setError(
                caught instanceof ApiError
                  ? apiErrorCopy(caught.code)
                  : zhCN.errors.fallback,
              );
            })
            .finally(() => setBusy(false));
        }}
      >
        {zhCN.export.action}
      </button>
      {error === undefined ? null : <p role="alert">{error}</p>}
      {atomicSuccess && exportJob !== undefined ? (
        <nav aria-label={zhCN.export.downloadRegion}>
          <ul className="export-artifacts">
            {DOWNLOADS.map(({ kind, label }) => (
              <li key={kind}>
                <a href={exportDownloadPath(exportJob.id, kind)} download>
                  {label}
                </a>
                <small>{zhCN.export.published}</small>
              </li>
            ))}
          </ul>
        </nav>
      ) : (
        <ul className="export-artifacts">
          {DOWNLOADS.map(({ kind }) => (
            <li key={kind}>
              <span>{zhCN.export.artifacts[kind]}</span>
              <small>{zhCN.workbench.unknown}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
