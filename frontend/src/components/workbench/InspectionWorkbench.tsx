import { useEffect, useMemo, useRef, useState } from "react";

import type {
  BalloonOverlay,
  ExportJob,
  OverlayBox,
  PdfDocumentLike,
  PdfPageTransform,
  PostJson,
  ProjectWorkbenchSipMetadataSuggestion,
  ReviewCommand,
  ReviewItem,
  ReviewWorkingCopyView,
} from "../../api/types";
import { projectStateCopy, zhCN } from "../../copy/zhCN";
import { BalloonToolbar } from "../balloons/BalloonToolbar";
import { PdfWorkspace } from "../pdf/PdfWorkspace";
import { ReviewPanel } from "../review/ReviewPanel";
import { ExportPanel } from "./ExportPanel";
import {
  InspectionItemTable,
  type PendingSourceReview,
} from "./InspectionItemTable";
import { SourceReviewPanel } from "./SourceReviewPanel";
import {
  saveDraftHandlesInOrder,
  type DraftSaveHandle,
} from "./draftSave";
import {
  inspectionItemPresentation,
  isReviewRequiredItem,
} from "./inspectionItemPresentation";
import {
  RecognitionSummary,
  type InspectionFilter,
} from "./RecognitionSummary";
import {
  SipInformationPanel,
  type MetadataDraft,
} from "./SipInformationPanel";
import { TechnicalRequirementPanel } from "./TechnicalRequirementPanel";
import "../../styles/workbench.css";


type InspectionWorkbenchProps = {
  pdfDocument: PdfDocumentLike | null;
  pageCount?: number;
  candidates: OverlayBox[];
  sources: OverlayBox[];
  balloons: BalloonOverlay[];
  pageTransforms?: PdfPageTransform[];
  items: ReviewItem[];
  sipMetadataSuggestions?: ProjectWorkbenchSipMetadataSuggestion[];
  onSave: (command: ReviewCommand) => Promise<void>;
  workingCopy?: ReviewWorkingCopyView;
  balloonBlockers?: string[];
  busy?: boolean;
  onPrepareReview?: () => Promise<void>;
  onConfirmReview?: () => Promise<string>;
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
  onReset?: () => void;
};

const NO_SELECTED_REVIEW_ITEM_ID = "__no_selected_review_item__";
const SIP_METADATA_FIELDS = [
  "material_code",
  "material_name",
  "drawing_number",
  "material",
  "revision",
] as const;
const SIP_DETAIL_TEXT_FIELDS = [
  "inspection_item",
  "inspection_standard",
  "inspection_method",
  "key_dimension",
  "inspection_role",
] as const;
const NO_SIP_METADATA_SUGGESTIONS: ProjectWorkbenchSipMetadataSuggestion[] = [];


function hasResolvedReview(workingCopy: ReviewWorkingCopyView): boolean {
  const blocking = Number(workingCopy.coverage.blocking_count ?? 0);
  const unresolved = Number(workingCopy.coverage.review_required_count ?? 0);
  return (
    blocking === 0
    && unresolved === 0
    && hasConfirmedSipMetadata(workingCopy)
    && workingCopy.items
      .filter((item) => item.active)
      .every(
        (item) =>
          item.requires_confirmation !== true
          && item.balloon_required !== null
          && item.balloon_required !== undefined
          && item.sip_detail_fields_confirmed === true
          && (item.sip_mapping_exceptions?.length ?? 0) === 0
          && SIP_DETAIL_TEXT_FIELDS.every(
            (field) => typeof item[field] === "string" && item[field]!.trim() !== "",
          )
          && Number.isInteger(item.source_page)
          && Number(item.source_page) >= 1,
      )
  );
}


function hasConfirmedSipMetadata(
  workingCopy: ReviewWorkingCopyView,
): boolean {
  const metadata = workingCopy.sip_metadata;
  return (
    metadata !== undefined
    && Object.keys(metadata).length === SIP_METADATA_FIELDS.length
    && SIP_METADATA_FIELDS.every(
      (field) => typeof metadata[field] === "string" && metadata[field]!.trim() !== "",
    )
  );
}


function hasContinuousFormalNumbers(balloons: BalloonOverlay[]): boolean {
  const numbers = balloons
    .filter((balloon) => balloon.status !== "deleted")
    .map((balloon) => balloon.number)
    .sort((left, right) => left - right);
  return numbers.length > 0
    && numbers.every((number, index) => number === index + 1);
}


function metadataDraft(
  workingCopy?: ReviewWorkingCopyView,
  suggestions: ProjectWorkbenchSipMetadataSuggestion[] = (
    NO_SIP_METADATA_SUGGESTIONS
  ),
): MetadataDraft {
  const suggestedValues = new Map(
    suggestions.map((suggestion) => [suggestion.field, suggestion.value]),
  );
  return Object.fromEntries(
    SIP_METADATA_FIELDS.map((field) => {
      const confirmed = workingCopy?.sip_metadata?.[field];
      return [
        field,
        typeof confirmed === "string" && confirmed.trim() !== ""
          ? confirmed
          : suggestedValues.get(field) ?? "",
      ];
    }),
  ) as MetadataDraft;
}


export function InspectionWorkbench({
  pdfDocument,
  pageCount,
  candidates,
  sources,
  balloons,
  pageTransforms,
  items,
  sipMetadataSuggestions = NO_SIP_METADATA_SUGGESTIONS,
  onSave,
  workingCopy,
  balloonBlockers = [],
  busy = false,
  onPrepareReview,
  onConfirmReview,
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
  onReset,
}: InspectionWorkbenchProps) {
  const [saveState, setSaveState] = useState<string>(zhCN.workbench.saved);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [selectedItemId, setSelectedItemId] = useState<string | undefined>(
    () => items.find(isReviewRequiredItem)?.item_id,
  );
  const [selectedBalloonId, setSelectedBalloonId] = useState<string>();
  const [selectedSourceId, setSelectedSourceId] = useState<string>();
  const [pageIndex, setPageIndex] = useState(0);
  const [filter, setFilter] = useState<InspectionFilter>("all");
  const [metadata, setMetadata] = useState<MetadataDraft>(
    () => metadataDraft(workingCopy, sipMetadataSuggestions),
  );
  const [reviewDraftDirty, setReviewDraftDirty] = useState(false);
  const [sourceDraftDirty, setSourceDraftDirty] = useState(false);
  const [selectedSipDraftDirty, setSelectedSipDraftDirty] = useState(false);
  const [
    technicalRequirementDraftDirty,
    setTechnicalRequirementDraftDirty,
  ] = useState(false);
  const [metadataDraftDirty, setMetadataDraftDirty] = useState(false);
  const [selectionBlocked, setSelectionBlocked] = useState(false);
  const [returnDialogOpen, setReturnDialogOpen] = useState(false);
  const [returnSaving, setReturnSaving] = useState(false);
  const reviewDraftSaveRef = useRef<DraftSaveHandle>(null);
  const sourceDraftSaveRef = useRef<DraftSaveHandle>(null);
  const selectedSipDraftSaveRef = useRef<DraftSaveHandle>(null);
  const technicalRequirementDraftSaveRef = useRef<DraftSaveHandle>(null);
  const returnActionRef = useRef<HTMLButtonElement>(null);
  const saveAndReturnRef = useRef<HTMLButtonElement>(null);
  const prepareAttemptRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (metadataDraftDirty) return;
    setMetadata(metadataDraft(workingCopy, sipMetadataSuggestions));
  }, [
    metadataDraftDirty,
    sipMetadataSuggestions,
    workingCopy?.version,
  ]);
  useEffect(() => {
    if (!reviewDraftDirty) setSelectionBlocked(false);
  }, [reviewDraftDirty]);
  useEffect(() => {
    if (returnDialogOpen) saveAndReturnRef.current?.focus();
  }, [returnDialogOpen]);
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
      })
      .filter((source) => /\d/.test(source.rawText));
  }, [sources, workingCopy?.coverage.entries]);
  useEffect(() => {
    if (
      selectedSourceId !== undefined
      && !pendingSources.some((source) => source.sourceId === selectedSourceId)
    ) {
      setSelectedSourceId(undefined);
    }
  }, [pendingSources, selectedSourceId]);

  const finalized = projectState === "reviewed";
  const localDraftDirty =
    reviewDraftDirty
    || sourceDraftDirty
    || selectedSipDraftDirty
    || technicalRequirementDraftDirty
    || metadataDraftDirty;
  const displayedSaveState = saving
    ? zhCN.workbench.saving
    : saveState === zhCN.workbench.saveFailed
      ? zhCN.workbench.saveFailed
      : selectionBlocked
        ? zhCN.workbench.finishCurrentEdit
        : localDraftDirty
          ? zhCN.workbench.pending
          : zhCN.workbench.saved;
  const visibleSaveState =
    selectionBlocked
    || saveState === zhCN.workbench.saveFailed
    || localDraftDirty
    ? displayedSaveState
    : actionState ?? displayedSaveState;
  const reviewImmutable =
    finalized || (workingCopy !== undefined && workingCopy.items_frozen_at !== null);
  const reviewCommandsDisabled =
    saving
    || busy
    || returnSaving
    || reviewImmutable;
  const frozen = workingCopy?.items_frozen_at != null;
  const activeBalloonCount = balloons.filter(
    (balloon) => balloon.status !== "deleted",
  ).length;
  const canPrepareReview =
    workingCopy !== undefined
    && !finalized
    && !busy
    && !saving
    && !localDraftDirty
    && hasResolvedReview(workingCopy)
    && (!frozen || activeBalloonCount === 0);
  const canFinalize =
    workingCopy !== undefined
    && frozen
    && !workingCopy.numbering_stale
    && balloonBlockers.length === 0
    && hasContinuousFormalNumbers(balloons)
    && !busy
    && !saving
    && !localDraftDirty;
  useEffect(() => {
    if (!canPrepareReview || onPrepareReview === undefined || workingCopy === undefined) {
      return;
    }
    const attemptKey = [
      workingCopy.id,
      workingCopy.version,
      frozen ? "frozen" : "editable",
      activeBalloonCount,
    ].join(":");
    if (prepareAttemptRef.current === attemptKey) return;
    prepareAttemptRef.current = attemptKey;
    void onPrepareReview().catch(() => undefined);
  }, [
    activeBalloonCount,
    canPrepareReview,
    frozen,
    onPrepareReview,
    workingCopy,
  ]);
  const submitCommand = async (command: ReviewCommand): Promise<boolean> => {
    if (
      savingRef.current
      || busy
      || reviewImmutable
    ) return false;
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
  const confirmMetadata = async (): Promise<boolean> => {
    const saved = await submitCommand({
      type: "set_sip_metadata",
      ...metadata,
    });
    if (saved) setMetadataDraftDirty(false);
    return saved;
  };
  const cancelMetadata = (): void => {
    setMetadata(metadataDraft(workingCopy, sipMetadataSuggestions));
    setMetadataDraftDirty(false);
  };
  const requestReturnToDrawingList = (): void => {
    if (onReset === undefined) return;
    if (!localDraftDirty) {
      onReset();
      return;
    }
    setReturnDialogOpen(true);
  };
  const cancelReturnToDrawingList = (): void => {
    if (returnSaving) return;
    setReturnDialogOpen(false);
    window.setTimeout(() => returnActionRef.current?.focus(), 0);
  };
  const saveAndReturnToDrawingList = async (): Promise<void> => {
    if (returnSaving || onReset === undefined) return;
    const remainingDraftSaveHandles = [
      reviewDraftSaveRef.current,
      sourceDraftSaveRef.current,
      selectedSipDraftSaveRef.current,
    ];
    setReturnSaving(true);
    try {
      const technicalRequirementSaved = await saveDraftHandlesInOrder([
        technicalRequirementDraftSaveRef.current,
      ]);
      if (!technicalRequirementSaved) {
        setSaveState(zhCN.workbench.saveFailed);
        return;
      }
      if (metadataDraftDirty && !(await confirmMetadata())) return;
      const saved = await saveDraftHandlesInOrder(
        remainingDraftSaveHandles,
      );
      if (!saved) {
        setSaveState(zhCN.workbench.saveFailed);
        return;
      }
      setReturnDialogOpen(false);
      onReset();
    } finally {
      setReturnSaving(false);
    }
  };
  const reviewedCount = items.filter(
    (item) => item.active && item.status === "kept",
  ).length;
  const activeItemCount = items.filter((item) => item.active).length;
  const readyItemCount = items.filter(
    (item) =>
      item.active
      && item.sip_detail_fields_confirmed === true
      && (item.sip_mapping_exceptions?.length ?? 0) === 0,
  ).length;
  const sipExceptionCount = items.filter(
    (item) =>
      item.active && (item.sip_mapping_exceptions?.length ?? 0) > 0,
  ).length;
  const sipRegenerationRequired = items.some(
    (item) =>
      item.active
      && item.sip_mapping_exceptions?.includes("sip_regeneration_required"),
  );
  const pendingSipItemCount = activeItemCount
    - readyItemCount
    - sipExceptionCount;
  const selectedReviewItem = items.find(
    (item) => item.active && item.item_id === selectedItemId,
  );
  const selectedReviewBalloon = balloons.find(
    (balloon) =>
      balloon.status !== "deleted" && balloon.itemId === selectedReviewItem?.item_id,
  );
  const selectedItemPresentation = selectedReviewItem === undefined
    ? undefined
    : inspectionItemPresentation(
        selectedReviewItem,
        selectedReviewBalloon,
        candidateNumbers.get(selectedReviewItem.item_id),
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
    if (!pendingSources.some((source) => source.sourceId === sourceId)) {
      return false;
    }
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
  const selectNextException = (
    justResolvedItemId?: string,
  ): boolean => {
    const exceptionItems = items.filter(
      (item) =>
        item.active
        && (
          (item.sip_mapping_exceptions?.length ?? 0) > 0
        )
        && item.item_id !== justResolvedItemId,
    );
    if (exceptionItems.length === 0) return false;
    const justResolvedIndex = justResolvedItemId === undefined
      ? -1
      : items.findIndex((item) => item.item_id === justResolvedItemId);
    const next = justResolvedIndex < 0
      ? exceptionItems[0]
      : exceptionItems.find(
        (item) => items.indexOf(item) > justResolvedIndex,
      ) ?? exceptionItems[0];
    setFilter("all");
    return selectItem(next.item_id);
  };
  const exportPanel = projectId === undefined || exportPost === undefined
    ? null
    : (
      <ExportPanel
        projectId={projectId}
        reviewedResultId={reviewedResultId}
        canFinalize={canFinalize}
        sipPendingCount={pendingSipItemCount}
        sipExceptionCount={sipExceptionCount}
        projectMetadataConfirmed={
          workingCopy !== undefined && hasConfirmedSipMetadata(workingCopy)
        }
        balloonBlockers={balloonBlockers}
        post={exportPost}
        initialExport={initialExport}
        onConfirmReview={onConfirmReview}
      />
    );
  const metadataValues: Array<readonly [string, string | undefined]> = [
    [zhCN.workbench.metadataFields.materialCode, metadata.material_code],
    [zhCN.workbench.metadataFields.materialName, metadata.material_name],
    [zhCN.workbench.metadataFields.drawingNumber, metadata.drawing_number],
    [zhCN.workbench.metadataFields.revision, metadata.revision],
    [zhCN.workbench.metadataFields.material, metadata.material],
  ];
  const auxiliaryPanel = (
    <aside
      className="workbench-aside"
      aria-label={zhCN.workbench.asideRegion}
    >
      {exportPanel}
      <SipInformationPanel
        metadata={metadata}
        metadataValues={metadataValues}
        persistedMetadata={workingCopy?.sip_metadata ?? {}}
        metadataSuggestions={sipMetadataSuggestions}
        metadataDirty={metadataDraftDirty}
        disabled={reviewCommandsDisabled}
        selectedItem={selectedReviewItem}
        selectedBalloon={selectedReviewBalloon}
        selectedSourceActive={selectedSourceId !== undefined}
        pendingItemCount={pendingSipItemCount}
        readyItemCount={readyItemCount}
        exceptionItemCount={sipExceptionCount}
        regenerationRequired={sipRegenerationRequired}
        onMetadataChange={(next) => {
          setMetadata(next);
          setMetadataDraftDirty(true);
        }}
        onConfirmMetadata={confirmMetadata}
        onCancelMetadata={cancelMetadata}
        onSelectNextException={() => {
          selectNextException();
        }}
        onSelectedSipConfirmed={(itemId) => {
          selectNextException(itemId);
        }}
        onCommand={submitCommand}
        onSelectedSipDraftChange={setSelectedSipDraftDirty}
        selectedSipDraftSaveRef={selectedSipDraftSaveRef}
      />
      <section className="company-log" aria-label={zhCN.workbench.companyLog}>
        <h2>{zhCN.workbench.companyLog}</h2>
        <p>{zhCN.workbench.emptyCompanyLog}</p>
      </section>
    </aside>
  );

  return (
    <main className="workbench-shell">
      <section
        className="workbench-compact-header"
        role="group"
        aria-label="项目与审核操作"
      >
        <div className="workbench-compact-header__summary-row">
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
                <dd>
                  {pendingSipItemCount > 0
                    ? `待生成 ${pendingSipItemCount} / 已生成 ${readyItemCount} / 异常 ${sipExceptionCount}`
                    : `已生成 ${readyItemCount} / 异常 ${sipExceptionCount}`}
                </dd>
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
          {onReset === undefined ? null : (
            <button
              ref={returnActionRef}
              type="button"
              className="workbench-reset-action"
              onClick={requestReturnToDrawingList}
            >
              {zhCN.workbench.returnToDrawingList}
            </button>
          )}
        </div>

      </section>

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
            selectedItemId={selectedItemId ?? NO_SELECTED_REVIEW_ITEM_ID}
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
          className={[
            "inspection-pane",
            (workingCopy?.technical_requirements?.length ?? 0) > 0
              ? "inspection-pane--with-technical-requirements"
              : "",
          ].filter(Boolean).join(" ")}
          aria-label={zhCN.workbench.reviewRegion}
          role="region"
        >
          <RecognitionSummary
            items={items}
            balloons={balloons}
            pendingSourceCount={pendingSources.length}
            manualReviewCount={workingCopy?.manual_review_count ?? 0}
            filter={filter}
            onFilterChange={setFilter}
          />
          <TechnicalRequirementPanel
            requirements={workingCopy?.technical_requirements ?? []}
            items={items}
            disabled={reviewCommandsDisabled}
            onSelectItem={(itemId) => {
              setFilter("all");
              return selectItem(itemId);
            }}
            onCommand={submitCommand}
            onDraftChange={setTechnicalRequirementDraftDirty}
            draftSaveRef={technicalRequirementDraftSaveRef}
          />
          <div
            className="inspection-review-workspace"
            role="group"
            aria-label={zhCN.workbench.mergedReviewWorkspace}
          >
            <div className="inspection-review-workspace__list">
              <InspectionItemTable
                compact
                items={items}
                balloons={balloons}
                pendingSources={pendingSources}
                candidateNumbers={candidateNumbers}
                filter={filter}
                selectedItemId={selectedItemId}
                selectedSourceId={selectedSourceId}
                onSelectItem={selectItem}
                onSelectSource={selectSource}
              />
            </div>
            <div className="inspection-review-workspace__detail">
              <SourceReviewPanel
                pendingSources={pendingSources}
                selectedSourceId={selectedSourceId}
                disabled={reviewCommandsDisabled}
                onCommand={submitCommand}
                onDraftChange={setSourceDraftDirty}
                draftSaveRef={sourceDraftSaveRef}
              />
              {selectedSourceId === undefined ? (
                <ReviewPanel
                  items={items}
                  disabled={reviewCommandsDisabled}
                  selectedItemId={selectedItemId}
                  selectedItemPresentation={selectedItemPresentation}
                  onSelectItem={selectItem}
                  pageIndex={pageIndex}
                  onCommand={submitCommand}
                  onDraftChange={setReviewDraftDirty}
                  draftSaveRef={reviewDraftSaveRef}
                />
              ) : null}
            </div>
          </div>
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
        </section>

      </div>
      {returnDialogOpen ? (
        <div className="workbench-return-dialog-backdrop">
          <section
            className="workbench-return-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workbench-return-dialog-title"
            aria-describedby="workbench-return-dialog-description"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                cancelReturnToDrawingList();
                return;
              }
              if (event.key !== "Tab") return;
              const buttons = Array.from(
                event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  "button:not(:disabled)",
                ),
              );
              if (buttons.length === 0) return;
              const first = buttons[0];
              const last = buttons[buttons.length - 1];
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
              }
            }}
          >
            <h2 id="workbench-return-dialog-title">
              {zhCN.workbench.returnDialogTitle}
            </h2>
            <p id="workbench-return-dialog-description">
              {zhCN.workbench.returnDialogDescription}
            </p>
            <div className="workbench-return-dialog__actions">
              <button
                ref={saveAndReturnRef}
                type="button"
                className="workbench-return-dialog__primary"
                disabled={returnSaving}
                onClick={() => void saveAndReturnToDrawingList()}
              >
                {returnSaving
                  ? zhCN.workbench.saving
                  : zhCN.workbench.saveAndReturn}
              </button>
              <button
                type="button"
                disabled={returnSaving}
                onClick={() => {
                  setReturnDialogOpen(false);
                  onReset?.();
                }}
              >
                {zhCN.workbench.discardAndReturn}
              </button>
              <button
                type="button"
                disabled={returnSaving}
                onClick={cancelReturnToDrawingList}
              >
                {zhCN.workbench.cancelReturn}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
