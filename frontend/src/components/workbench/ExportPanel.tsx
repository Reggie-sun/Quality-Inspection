import { useState } from "react";

import type { ExportJob, PostJson } from "../../api/types";
import { createExport, exportDownloadPath } from "../../features/exports/api";


type ExportPanelProps = {
  projectId: string;
  reviewedResultId?: string;
  balloonBlockers: string[];
  post: PostJson;
};

const DOWNLOADS = [
  { kind: "ballooned_pdf" as const, label: "Download ballooned PDF" },
  { kind: "sip_excel" as const, label: "Download SIP Excel" },
  { kind: "manifest" as const, label: "Download manifest" },
];


export function ExportPanel({
  projectId,
  reviewedResultId,
  balloonBlockers,
  post,
}: ExportPanelProps) {
  const [exportJob, setExportJob] = useState<ExportJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const canExport = reviewedResultId !== undefined && balloonBlockers.length === 0;
  const downloadableKinds = new Set(
    exportJob?.artifacts
      .filter((artifact) => artifact.downloadable)
      .map((artifact) => artifact.kind) ?? [],
  );
  const atomicSuccess = exportJob?.status === "success"
    && DOWNLOADS.every(({ kind }) => downloadableKinds.has(kind))
    && downloadableKinds.size === DOWNLOADS.length;

  return (
    <section className="export-panel" aria-label="Formal export">
      <div>
        <strong>Formal package</strong>
        <small>
          {reviewedResultId === undefined
            ? "Confirm the immutable reviewed result first."
            : balloonBlockers.length > 0
              ? `${balloonBlockers.length} balloon blocker(s) remain.`
              : "PDF, SIP Excel and manifest publish atomically."}
        </small>
      </div>
      <button
        type="button"
        className="primary-action"
        disabled={!canExport || busy}
        onClick={() => {
          if (reviewedResultId === undefined) return;
          setBusy(true);
          setError(undefined);
          setExportJob(undefined);
          void createExport(post, projectId, reviewedResultId)
            .then((created) => {
              if (created.status !== "success") {
                throw new Error("formal export did not complete atomically");
              }
              setExportJob(created);
            })
            .catch((caught) => {
              setError(caught instanceof Error ? caught.message : "formal export failed");
            })
            .finally(() => setBusy(false));
        }}
      >
        {busy ? "Creating package…" : "Create formal export"}
      </button>
      {error === undefined ? null : <p role="alert">{error}</p>}
      {!atomicSuccess || exportJob === undefined ? null : (
        <nav className="export-downloads" aria-label="Formal downloads">
          {DOWNLOADS.map(({ kind, label }) => (
            <a key={kind} href={exportDownloadPath(exportJob.id, kind)} download>
              {label}
            </a>
          ))}
        </nav>
      )}
    </section>
  );
}
