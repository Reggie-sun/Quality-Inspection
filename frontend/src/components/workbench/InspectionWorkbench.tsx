import { useState } from "react";

import type {
  BalloonOverlay,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { PdfWorkspace } from "../pdf/PdfWorkspace";
import { ReviewPanel } from "../review/ReviewPanel";


type InspectionWorkbenchProps = {
  pdfDocument: PdfDocumentLike | null;
  pageCount?: number;
  candidates: OverlayBox[];
  sources: OverlayBox[];
  balloons: BalloonOverlay[];
  pageTransforms?: PdfPageTransform[];
  items: ReviewItem[];
  onSave: (command: ReviewCommand) => Promise<void>;
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
}: InspectionWorkbenchProps) {
  const [pendingCommand, setPendingCommand] = useState<ReviewCommand>();
  const [saveState, setSaveState] = useState("No pending changes");
  const [saving, setSaving] = useState(false);

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
    <main>
      <header>
        <h1>Quality Inspection Review</h1>
        <p>{saveState}</p>
        <button
          type="button"
          disabled={pendingCommand === undefined || saving}
          onClick={() => void save()}
        >
          Save working copy
        </button>
      </header>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 3fr) minmax(320px, 2fr)",
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
        />
        <ReviewPanel
          items={items}
          disabled={pendingCommand !== undefined}
          onCommand={(command) => {
            setPendingCommand(command);
            setSaveState(`Pending command: ${command.type}`);
          }}
        />
      </div>
    </main>
  );
}
