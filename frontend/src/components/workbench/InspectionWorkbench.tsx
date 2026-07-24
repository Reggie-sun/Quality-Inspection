import { useEffect, useMemo, useRef, useState } from "react";

import type {
  BalloonOverlay,
  ExportJob,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  PostJson,
  ReviewCommand,
  ReviewItem,
  ReviewWorkingCopy,
} from "../../api/types";
import { projectStateCopy, zhCN } from "../../copy/zhCN";
import { BalloonToolbar } from "../balloons/BalloonToolbar";
import { PdfWorkspace } from "../pdf/PdfWorkspace";
import { ReviewPanel } from "../review/ReviewPanel";
import { ExportPanel } from "./ExportPanel";
import { FreezeReviewButton } from "./FreezeReviewButton";
import {
  InspectionItemTable,
  SelectedInspectionItemSummary,
  type PendingSourceReview,
} from "./InspectionItemTable";
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
  initialExport?: ExportJob | null;
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
  initialExport,
  exportPost,
  actionState,
}: InspectionWorkbenchProps) {
  const [saveState, setSaveState] = useState<string>(zhCN.workbench.saved);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [selectedItemId, setSelectedItemId] = useState<string | undefined>(
    () => items.find((item) => item.active)?.item_id,
  );
  const [selectedBalloonId, setSelectedBalloonId] = useState<string>();
  const [selectedSourceId, setSelectedSourceId] = useState<string>();
  const [pageIndex, setPageIndex] = useState(0);
  const [filter, setFilter] = useState<InspectionFilter>("all");
  const [metadata, setMetadata] = useState<MetadataDraft>(
    () => metadataDraft(workingCopy),
  );
  const [reviewDraftDirty, setReviewDraftDirty] = useState(false);
  const [sipDraftDirty, setSipDraftDirty] = useState(false);
  const [metadataDraftDirty, setMetadataDraftDirty] = useState(false);
  const [selectionBlocked, setSelectionBlocked] = useState(false);
  useEffect(() => {
    setMetadata(metadataDraft(workingCopy));
    setMetadataDraftDirty(false);
  }, [workingCopy?.version]);
  useEffect(() => {
    if (!reviewDraftDirty) setSelectionBlocked(false);
  }, [reviewDraftDirty]);
  const candidateNumbers = useMemo(() => {
    const lookup = new Map<string, number>();
    for (const candidate of candidates) {
      if (
        candidate.itemId !== undefined
        && candidate.candidateNumber !== undefined
        && !lookup.has(candidate.itemId)
      ) {
        lookup.set(candidate.itemId, candidate.candidateNumber);
      }
    }
    return lookup;
  }, [candidates]);
  const pendingSources = useMemo<PendingSourceReview[]>(() => {
    if (workingCopy === undefined) return [];
    return (workingCopy.coverage.entries ?? [])
      .filter(
        (entry) =>
          entry.requires_confirmation === true
          && (entry.candidate_id === null || entry.candidate_id === undefined),
      )
      .map((entry) => {
        const source = sources.find(
          (candidate) => candidate.id === entry.source_location_id,
        );
        return {
          observationId: entry.observation_id,
          sourceId: entry.source_location_id,
          rawText: source?.rawText?.trim() ?? "",
          coordinates: entry.coordinates,
          pageIndex: source?.pageIndex,
        };
      });
  }, [sources, workingCopy?.coverage.entries]);

  const finalized = projectState === "reviewed";
  const localDraftDirty =
    reviewDraftDirty || sipDraftDirty || metadataDraftDirty;
  const displayedSaveState = selectionBlocked
    ? zhCN.workbench.finishCurrentEdit
    : saving
      ? zhCN.workbench.saving
      : saveState === zhCN.workbench.saveFailed
        ? zhCN.workbench.saveFailed
        : localDraftDirty
          ? zhCN.workbench.pending
          : zhCN.workbench.saved;
  const visibleSaveState =
    selectionBlocked || saveState === zhCN.workbench.saveFailed
    ? displayedSaveState
    : actionState ?? displayedSaveState;
  const reviewImmutable =
    finalized || (workingCopy !== undefined && workingCopy.items_frozen_at !== null);
  const submitCommand = async (command: ReviewCommand): Promise<boolean> => {
    if (savingRef.current || busy || reviewImmutable) return false;
    savingRef.current = true;
    setSaving(true);
    setSaveState(zhCN.workbench.saving);
    try {
      await onSave(command);
      setSaveState(zhCN.workbench.saved);
      return true;
    } catch {
      setSaveState(zhCN.workbench.saveFailed);
      return false;
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };
  const reviewedCount = items.filter(
    (item) => item.active && item.status === "kept",
  ).length;
  const confirmedCount = items.filter(
    (item) => item.active && item.sip_detail_fields_confirmed === true,
  ).length;
  const selectedReviewItem = items.find(
    (item) => item.active && item.item_id === selectedItemId,
  );
  const selectedReviewBalloon = balloons.find(
    (balloon) =>
      balloon.status !== "deleted" && balloon.itemId === selectedReviewItem?.item_id,
  );
  const selectItem = (itemId: string): boolean => {
    if (reviewDraftDirty && itemId !== selectedItemId) {
      setSelectionBlocked(true);
      return false;
    }
    setSelectionBlocked(false);
    setSelectedItemId(itemId);
    setSelectedSourceId(undefined);
    const item = items.find((candidate) => candidate.item_id === itemId);
    const balloon = balloons.find(
      (candidate) =>
        candidate.status !== "deleted" && candidate.itemId === itemId,
    );
    setSelectedBalloonId(balloon?.id);
    setPageIndex(item?.page_index ?? balloon?.pageIndex ?? pageIndex);
    return true;
  };
  const selectSource = (sourceId: string): boolean => {
    if (reviewDraftDirty && sourceId !== selectedSourceId) {
      setSelectionBlocked(true);
      return false;
    }
    setSelectionBlocked(false);
    setSelectedItemId(undefined);
    setSelectedSourceId(sourceId);
    setSelectedBalloonId(undefined);
    const source = sources.find((candidate) => candidate.id === sourceId);
    setPageIndex(source?.pageIndex ?? pageIndex);
    return true;
  };
  const exportPanel = projectId === undefined || exportPost === undefined
    ? null
    : (
      <ExportPanel
        projectId={projectId}
        reviewedResultId={reviewedResultId}
        balloonBlockers={balloonBlockers}
        post={exportPost}
        initialExport={initialExport}
      />
    );
  const metadataValues: Array<readonly [string, string | undefined]> = [
    [zhCN.workbench.metadataFields.materialName, metadata.material_name],
    [zhCN.workbench.metadataFields.drawingNumber, metadata.drawing_number],
    [zhCN.workbench.metadataFields.revision, metadata.revision],
    [zhCN.workbench.metadataFields.material, metadata.material],
    [zhCN.workbench.metadataFields.unit, undefined],
    [
      zhCN.workbench.metadataFields.inspectionStandard,
      selectedReviewItem?.inspection_standard,
    ],
    [
      zhCN.workbench.metadataFields.inspectionRole,
      selectedReviewItem?.inspection_role,
    ],
    [zhCN.workbench.metadataFields.reviewerRole, undefined],
  ];
  const auxiliaryPanel = (
    <aside
      className="workbench-aside"
      aria-label={zhCN.workbench.asideRegion}
    >
      {workingCopy === undefined ? null : (
        <section
          className="sip-metadata-card"
          aria-label={zhCN.workbench.metadata}
          role="region"
        >
          <h2>{zhCN.workbench.metadata}</h2>
          <dl className="sip-metadata-summary">
            {metadataValues.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd title={value}>{value || zhCN.workbench.unknown}</dd>
              </div>
            ))}
          </dl>
          <details className="sip-metadata-editor">
            <summary>{zhCN.workbench.editMetadata}</summary>
            <fieldset
              disabled={saving || busy || reviewImmutable}
            >
              <legend className="visually-hidden">
                {zhCN.workbench.editMetadata}
              </legend>
              {(
                [
                  ["material_code", zhCN.workbench.metadataFields.materialCode],
                  ["material_name", zhCN.workbench.metadataFields.materialName],
                  ["drawing_number", zhCN.workbench.metadataFields.drawingNumber],
                  ["revision", zhCN.workbench.metadataFields.revision],
                  ["material", zhCN.workbench.metadataFields.material],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <input
                    aria-label={label}
                    value={metadata[key]}
                    placeholder={zhCN.workbench.unknown}
                    onChange={(event) => {
                      setMetadata({ ...metadata, [key]: event.target.value });
                      setMetadataDraftDirty(true);
                    }}
                  />
                </label>
              ))}
              <div className="sip-metadata-actions">
                <button
                  type="button"
                  disabled={Object.values(metadata).some(
                    (value) => value.trim() === "",
                  )}
                  onClick={() => {
                    void (async () => {
                      const saved = await submitCommand({
                        type: "set_sip_metadata",
                        ...metadata,
                      });
                      if (saved) setMetadataDraftDirty(false);
                    })();
                  }}
                >
                  {zhCN.workbench.confirmMetadata}
                </button>
                <button
                  type="button"
                  disabled={!metadataDraftDirty}
                  onClick={() => {
                    setMetadata(metadataDraft(workingCopy));
                    setMetadataDraftDirty(false);
                  }}
                >
                  {zhCN.workbench.cancelMetadata}
                </button>
              </div>
            </fieldset>
          </details>
        </section>
      )}
      {exportPanel}
      <section className="company-log" aria-label={zhCN.workbench.companyLog}>
        <h2>{zhCN.workbench.companyLog}</h2>
        <p>{zhCN.workbench.emptyCompanyLog}</p>
      </section>
    </aside>
  );

  return (
    <main className="workbench-shell">
      <section
        className="project-summary"
        role="region"
        aria-label={zhCN.workbench.projectSummary}
      >
        <dl>
          <div>
            <dt>{zhCN.workbench.productName}</dt>
            <dd>{metadata.material_name || zhCN.workbench.unknown}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.drawingNumber}</dt>
            <dd>{metadata.drawing_number || zhCN.workbench.unknown}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.revision}</dt>
            <dd>{metadata.revision || zhCN.workbench.unknown}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.drawingType}</dt>
            <dd>{zhCN.workbench.unknown}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.totalItems}</dt>
            <dd>{items.length}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.reviewedItems}</dt>
            <dd>{reviewedCount}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.confirmedItems}</dt>
            <dd>{confirmedCount}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.currentState}</dt>
            <dd>{projectStateCopy(projectState)}</dd>
          </div>
          <div>
            <dt>{zhCN.workbench.saveStatus}</dt>
            <dd role="status" aria-live="polite" aria-atomic="true">
              {visibleSaveState}
            </dd>
          </div>
        </dl>
      </section>

      {workingCopy === undefined
        || onFreeze === undefined
        || onGenerate === undefined
        || onConfirm === undefined
        ? null
        : (
          <section className="review-actions" aria-label="审核流程操作">
            <FreezeReviewButton
              workingCopy={workingCopy}
              balloons={balloons}
              balloonBlockers={balloonBlockers}
              busy={busy || saving || finalized || localDraftDirty}
              onFreeze={onFreeze}
              onGenerate={onGenerate}
              onConfirm={onConfirm}
            />
          </section>
        )}

      <div className="workbench-layout">
        <section
          className="drawing-pane"
          aria-label={zhCN.workbench.drawingRegion}
          role="region"
        >
          <PdfWorkspace
            pdfDocument={pdfDocument}
            pageCount={pageCount}
            candidates={candidates}
            sources={sources}
            balloons={balloons}
            pageTransforms={pageTransforms}
            selectedItemId={selectedItemId}
            selectedSourceId={selectedSourceId}
            selectedBalloonId={selectedBalloonId}
            onSelectItem={selectItem}
            onSelectSource={selectSource}
            onSelectBalloon={(itemId, balloonId) => {
              if (!selectItem(itemId)) return;
              setSelectedBalloonId(balloonId);
              const balloon = balloons.find((candidate) => candidate.id === balloonId);
              setPageIndex(balloon?.pageIndex ?? pageIndex);
            }}
            onMoveBalloon={finalized ? undefined : onMoveBalloon}
            onPageChange={setPageIndex}
            auxiliaryPanel={auxiliaryPanel}
          />
        </section>

        <section
          className="inspection-pane"
          aria-label={zhCN.workbench.reviewRegion}
          role="region"
        >
          <RecognitionSummary
            items={items}
            balloons={balloons}
            pendingSourceCount={pendingSources.length}
            filter={filter}
            onFilterChange={setFilter}
          />
          {selectedReviewItem === undefined ? null : (
            <SelectedInspectionItemSummary
              item={selectedReviewItem}
              balloon={selectedReviewBalloon}
              candidateNumber={candidateNumbers.get(selectedReviewItem.item_id)}
            />
          )}
          <InspectionItemTable
            items={items}
            balloons={balloons}
            pendingSources={pendingSources}
            candidateNumbers={candidateNumbers}
            filter={filter}
            selectedItemId={selectedItemId}
            selectedSourceId={selectedSourceId}
            disabled={saving || busy || reviewImmutable}
            onSelectItem={selectItem}
            onSelectSource={selectSource}
            onCommand={submitCommand}
            onDraftChange={setSipDraftDirty}
          />
          {onDeleteBalloon === undefined || onRebuildBalloon === undefined
          || onReorderBalloon === undefined || onRenumberBalloons === undefined
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
          <details className="candidate-editor" open>
            <summary>{zhCN.workbench.reviewCommands}</summary>
            <ReviewPanel
              items={items}
              disabled={saving || busy || reviewImmutable}
              selectedItemId={selectedItemId}
              onSelectItem={selectItem}
              pageIndex={pageIndex}
              onCommand={submitCommand}
              onDraftChange={setReviewDraftDirty}
            />
          </details>
        </section>

      </div>
    </main>
  );
}
