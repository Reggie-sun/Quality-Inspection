import { useEffect, useState } from "react";

import type {
  BalloonOverlay,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  PostJson,
  ReviewCommand,
  ReviewItem,
  ReviewWorkingCopy,
} from "../../api/types";
import { BalloonToolbar } from "../balloons/BalloonToolbar";
import { PdfWorkspace } from "../pdf/PdfWorkspace";
import { ReviewPanel } from "../review/ReviewPanel";
import { ExportPanel } from "./ExportPanel";
import { FreezeReviewButton } from "./FreezeReviewButton";
import { InspectionItemTable } from "./InspectionItemTable";
import {
  RecognitionSummary,
  type InspectionFilter,
} from "./RecognitionSummary";
import "../../styles/workbench.css";


type InspectionWorkbenchProps = {
  pdfDocument: PdfDocumentLike | null;
  pageCount?: number;
  candidates: OverlayBox[];
  sources: OverlayBox[];
  balloons: BalloonOverlay[];
  pageTransforms?: PdfPageTransform[];
  items: ReviewItem[];
  onSave: (command: ReviewCommand) => Promise<void>;
  workingCopy?: ReviewWorkingCopy;
  balloonBlockers?: string[];
  busy?: boolean;
  onFreeze?: () => void;
  onGenerate?: () => void;
  onConfirm?: () => void;
  onMoveBalloon?: (
    balloonId: string,
    expectedVersion: number,
    centerPdf: [number, number],
  ) => void;
  onDeleteBalloon?: (balloonId: string, expectedVersion: number) => void;
  onRebuildBalloon?: (balloonId: string, expectedVersion: number) => void;
  onReorderBalloon?: (
    balloonId: string,
    expectedVersion: number,
    sortOrder: number,
  ) => void;
  onRenumberBalloons?: (
    orderedIds: string[],
    expectedVersions: Record<string, number>,
  ) => void;
  projectState?: string;
  projectId?: string;
  reviewedResultId?: string;
  exportPost?: PostJson;
  operatorId?: string;
  actionState?: string;
};

type MetadataDraft = {
  material_code: string;
  material_name: string;
  drawing_number: string;
  material: string;
  revision: string;
};


function metadataDraft(workingCopy?: ReviewWorkingCopy): MetadataDraft {
  return {
    material_code: workingCopy?.sip_metadata?.material_code ?? "",
    material_name: workingCopy?.sip_metadata?.material_name ?? "",
    drawing_number: workingCopy?.sip_metadata?.drawing_number ?? "",
    material: workingCopy?.sip_metadata?.material ?? "",
    revision: workingCopy?.sip_metadata?.revision ?? "",
  };
}


export function InspectionWorkbench({
  pdfDocument,
  pageCount,
  candidates,
  sources,
  balloons,
  pageTransforms,
  items,
  onSave,
  workingCopy,
  balloonBlockers = [],
  busy = false,
  onFreeze,
  onGenerate,
  onConfirm,
  onMoveBalloon,
  onDeleteBalloon,
  onRebuildBalloon,
  onReorderBalloon,
  onRenumberBalloons,
  projectState,
  projectId,
  reviewedResultId,
  exportPost,
  operatorId,
  actionState,
}: InspectionWorkbenchProps) {
  const [pendingCommand, setPendingCommand] = useState<ReviewCommand>();
  const [saveState, setSaveState] = useState("No pending changes");
  const [saving, setSaving] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string>();
  const [selectedBalloonId, setSelectedBalloonId] = useState<string>();
  const [pageIndex, setPageIndex] = useState(0);
  const [filter, setFilter] = useState<InspectionFilter>("all");
  const [metadata, setMetadata] = useState<MetadataDraft>(() => metadataDraft(workingCopy));
  useEffect(() => setMetadata(metadataDraft(workingCopy)), [workingCopy?.version]);

  const finalized = projectState === "reviewed";
  const reviewImmutable =
    finalized || (workingCopy !== undefined && workingCopy.items_frozen_at !== null);
  const selectItem = (itemId: string) => {
    setSelectedItemId(itemId);
    setSelectedBalloonId(undefined);
    const item = items.find((candidate) => candidate.item_id === itemId);
    const balloon = balloons.find((candidate) => candidate.itemId === itemId);
    setPageIndex(item?.page_index ?? balloon?.pageIndex ?? pageIndex);
  };
  const queueCommand = (command: ReviewCommand) => {
    setPendingCommand(command);
    setSaveState(`Pending command: ${command.type}`);
  };

  const save = async () => {
    if (pendingCommand === undefined || saving) return;
    setSaving(true);
    setSaveState("Saving working copy…");
    try {
      await onSave(pendingCommand);
      setPendingCommand(undefined);
      setSaveState("Working copy saved");
    } catch {
      setSaveState("Save failed; working copy was not frozen");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="workbench-shell">
      <header className="workbench-header">
        <div>
          <p className="workbench-eyebrow">PDF BALLOON REVIEW</p>
          <h1>Quality Inspection Review</h1>
          <p className="workbench-context">
            {projectState === undefined ? "Local review" : `Project ${projectState}`}
            {operatorId === undefined ? "" : ` · Operator ${operatorId}`}
          </p>
        </div>
        <div className="workbench-save-state">
          {actionState === undefined ? null : <p role="status">{actionState}</p>}
          <p>{saveState}</p>
          <button
            type="button"
            className="primary-action"
            disabled={pendingCommand === undefined || saving || busy}
            onClick={() => void save()}
          >
            Save working copy
          </button>
        </div>
      </header>

      <div className="workbench-finalization">
        {workingCopy === undefined || onFreeze === undefined || onGenerate === undefined || onConfirm === undefined
          ? null
          : (
            <FreezeReviewButton
              workingCopy={workingCopy}
              balloons={balloons}
              balloonBlockers={balloonBlockers}
              busy={busy || finalized || pendingCommand !== undefined}
              onFreeze={onFreeze}
              onGenerate={onGenerate}
              onConfirm={onConfirm}
            />
          )}
        {projectId === undefined || exportPost === undefined ? null : (
          <ExportPanel
            projectId={projectId}
            reviewedResultId={reviewedResultId}
            balloonBlockers={balloonBlockers}
            post={exportPost}
          />
        )}
      </div>

      <div className="workbench-layout">
        <section className="drawing-pane" aria-label="Engineering drawing">
          <PdfWorkspace
            pdfDocument={pdfDocument}
            pageCount={pageCount}
            candidates={candidates}
            sources={sources}
            balloons={balloons}
            pageTransforms={pageTransforms}
            selectedItemId={selectedItemId}
            selectedBalloonId={selectedBalloonId}
            onSelectItem={selectItem}
            onSelectBalloon={(itemId, balloonId) => {
              setSelectedItemId(itemId);
              setSelectedBalloonId(balloonId);
              const balloon = balloons.find((candidate) => candidate.id === balloonId);
              setPageIndex(balloon?.pageIndex ?? pageIndex);
            }}
            onMoveBalloon={finalized ? undefined : onMoveBalloon}
            onPageChange={setPageIndex}
          />
        </section>

        <aside className="inspection-pane">
          <RecognitionSummary
            items={items}
            balloons={balloons}
            filter={filter}
            onFilterChange={setFilter}
          />
          {projectId === undefined ? null : (
            <InspectionItemTable
              items={items}
              balloons={balloons}
              filter={filter}
              selectedItemId={selectedItemId}
              disabled={pendingCommand !== undefined || busy || reviewImmutable}
              onSelectItem={selectItem}
              onCommand={queueCommand}
            />
          )}

          {onDeleteBalloon === undefined || onRebuildBalloon === undefined ||
          onReorderBalloon === undefined || onRenumberBalloons === undefined
            ? null
            : (
              <BalloonToolbar
                balloons={balloons}
                selectedBalloonId={selectedBalloonId}
                disabled={busy || finalized}
                onDelete={onDeleteBalloon}
                onRebuild={onRebuildBalloon}
                onReorder={onReorderBalloon}
                onRenumber={onRenumberBalloons}
              />
            )}

          {workingCopy === undefined ? null : (
            <fieldset className="sip-metadata" disabled={busy || reviewImmutable || pendingCommand !== undefined}>
              <legend>Drawing and SIP metadata</legend>
              {(
                [
                  ["material_code", "Material code"],
                  ["material_name", "Material name"],
                  ["drawing_number", "Drawing number"],
                  ["material", "Material"],
                  ["revision", "Revision"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    aria-label={label}
                    value={metadata[key]}
                    onChange={(event) => setMetadata({ ...metadata, [key]: event.target.value })}
                  />
                </label>
              ))}
              <button
                type="button"
                disabled={Object.values(metadata).some((value) => value.trim() === "")}
                onClick={() => queueCommand({ type: "set_sip_metadata", ...metadata })}
              >
                Confirm SIP metadata
              </button>
            </fieldset>
          )}

          <details className="candidate-editor" open>
            <summary>Candidate editing and review commands</summary>
            <ReviewPanel
              items={items}
              disabled={pendingCommand !== undefined || busy || reviewImmutable}
              selectedItemId={selectedItemId}
              onSelectItem={selectItem}
              pageIndex={pageIndex}
              onCommand={queueCommand}
            />
          </details>
        </aside>
      </div>
    </main>
  );
}
