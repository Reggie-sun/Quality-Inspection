import { useState } from "react";

import type {
  BalloonOverlay,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  ReviewCommand,
  ReviewItem,
  ReviewWorkingCopy,
} from "../../api/types";
import { BalloonToolbar } from "../balloons/BalloonToolbar";
import { PdfWorkspace } from "../pdf/PdfWorkspace";
import { ReviewPanel } from "../review/ReviewPanel";
import { FreezeReviewButton } from "./FreezeReviewButton";


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
  operatorId?: string;
  actionState?: string;
};


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
  operatorId,
  actionState,
}: InspectionWorkbenchProps) {
  const [pendingCommand, setPendingCommand] = useState<ReviewCommand>();
  const [saveState, setSaveState] = useState("No pending changes");
  const [saving, setSaving] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState<string>();
  const [selectedBalloonId, setSelectedBalloonId] = useState<string>();
  const [pageIndex, setPageIndex] = useState(0);
  const finalized = projectState === "reviewed";
  const reviewImmutable =
    finalized || (workingCopy !== undefined && workingCopy.items_frozen_at !== null);
  const selectItem = (itemId: string) => {
    setSelectedItemId(itemId);
    setSelectedBalloonId(undefined);
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
    <main style={{ maxWidth: 1760, margin: "0 auto", padding: 24, color: "#172033" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 20,
          alignItems: "flex-start",
          marginBottom: 16,
          padding: 18,
          background: "white",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          boxShadow: "0 8px 24px rgba(15, 23, 42, 0.05)",
        }}
      >
        <div>
          <p style={{ margin: 0, color: "#64748b", fontSize: 13, letterSpacing: 0.4 }}>
            PDF BALLOON REVIEW
          </p>
          <h1 style={{ margin: "4px 0", fontSize: 30, letterSpacing: -0.6 }}>
            Quality Inspection Review
          </h1>
          <p style={{ margin: 0, color: "#475569" }}>
            {projectState === undefined ? "Local review" : `Project ${projectState}`}
            {operatorId === undefined ? "" : ` · Operator ${operatorId}`}
          </p>
        </div>
        <div style={{ display: "grid", gap: 8, justifyItems: "end" }}>
          {actionState === undefined
            ? null
            : <p role="status" style={{ margin: 0 }}>{actionState}</p>}
          <p style={{ margin: 0 }}>{saveState}</p>
          <button
            type="button"
            disabled={pendingCommand === undefined || saving || busy}
            onClick={() => void save()}
          >
            Save working copy
          </button>
        </div>
      </header>
      {workingCopy === undefined || onFreeze === undefined || onGenerate === undefined || onConfirm === undefined
        ? null
        : (
          <div style={{ marginBottom: 16 }}>
            <FreezeReviewButton
              workingCopy={workingCopy}
              balloons={balloons}
              balloonBlockers={balloonBlockers}
              busy={busy || finalized || pendingCommand !== undefined}
              onFreeze={onFreeze}
              onGenerate={onGenerate}
              onConfirm={onConfirm}
            />
          </div>
        )}
      <div
        style={{
          display: "grid",
            gridTemplateColumns: "minmax(0, 1.65fr) minmax(420px, 1fr)",
          gap: 16,
          alignItems: "start",
        }}
      >
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
          }}
          onMoveBalloon={finalized ? undefined : onMoveBalloon}
          onPageChange={setPageIndex}
        />
        <aside
          style={{
            padding: 16,
            background: "white",
            border: "1px solid #e2e8f0",
            borderRadius: 12,
            maxHeight: "calc(100vh - 210px)",
            minHeight: 640,
            overflow: "auto",
          }}
        >
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
          <ReviewPanel
            items={items}
            disabled={pendingCommand !== undefined || busy || reviewImmutable}
            selectedItemId={selectedItemId}
            onSelectItem={selectItem}
            pageIndex={pageIndex}
            onCommand={(command) => {
              setPendingCommand(command);
              setSaveState(`Pending command: ${command.type}`);
            }}
          />
        </aside>
      </div>
    </main>
  );
}
