import { useEffect, useMemo, useState } from "react";

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
import { CoverageReviewPanel } from "../review/CoverageReviewPanel";
import { ReviewPanel } from "../review/ReviewPanel";
import { ExportPanel } from "./ExportPanel";
import { FreezeReviewButton } from "./FreezeReviewButton";
import {
  InspectionItemTable,
  SelectedInspectionItemSummary,
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
  const [pendingCommand, setPendingCommand] = useState<ReviewCommand>();
  const [saveState, setSaveState] = useState<string>(zhCN.workbench.saved);
  const [saving, setSaving] = useState(false);
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
  useEffect(() => setMetadata(metadataDraft(workingCopy)), [workingCopy?.version]);
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

  const finalized = projectState === "reviewed";
  const reviewImmutable =
    finalized || (workingCopy !== undefined && workingCopy.items_frozen_at !== null);
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
  const activeStage = initialExport?.status === "success" || reviewedResultId !== undefined
    ? 4
    : balloons.some((balloon) => balloon.status !== "deleted")
      || workingCopy?.items_frozen_at != null
      ? 3
      : 2;
  const selectItem = (itemId: string) => {
    setSelectedItemId(itemId);
    setSelectedSourceId(undefined);
    const item = items.find((candidate) => candidate.item_id === itemId);
    const balloon = balloons.find(
      (candidate) =>
        candidate.status !== "deleted" && candidate.itemId === itemId,
    );
    setSelectedBalloonId(balloon?.id);
    setPageIndex(item?.page_index ?? balloon?.pageIndex ?? pageIndex);
  };
  const queueCommand = (command: ReviewCommand) => {
    setPendingCommand(command);
    setSaveState(zhCN.workbench.pending);
  };
  const save = async () => {
    if (pendingCommand === undefined || saving) return;
    setSaving(true);
    setSaveState(zhCN.workbench.saving);
    try {
      await onSave(pendingCommand);
      setPendingCommand(undefined);
      setSaveState(zhCN.workbench.saved);
    } catch {
      setSaveState(zhCN.workbench.saveFailed);
    } finally {
      setSaving(false);
    }
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

  return (
    <main className="workbench-shell">
      <header className="workbench-header">
        <div>
          <p className="workbench-eyebrow">{zhCN.workbench.eyebrow}</p>
          <h1>{zhCN.workbench.title}</h1>
        </div>
        <div className="workbench-save-state">
          {actionState === undefined ? null : <p role="status">{actionState}</p>}
          <button
            type="button"
            className="primary-action"
            disabled={pendingCommand === undefined || saving || busy}
            onClick={() => void save()}
          >
            {zhCN.workbench.save}
          </button>
        </div>
        {workingCopy === undefined
          || onFreeze === undefined
          || onGenerate === undefined
          || onConfirm === undefined
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
      </header>

      <nav className="stage-rail" aria-label={zhCN.workbench.stageNavigation}>
        <ol>
          {zhCN.stages.map((stage, index) => (
            <li
              key={stage}
              data-state={index < activeStage ? "complete" : index === activeStage ? "active" : "pending"}
              aria-current={index === activeStage ? "step" : undefined}
            >
              <span aria-hidden="true" data-number={index + 1} />
              <strong>{stage}</strong>
            </li>
          ))}
        </ol>
      </nav>

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
            <dd>{saveState}</dd>
          </div>
        </dl>
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
            selectedItemId={selectedItemId}
            selectedSourceId={selectedSourceId}
            selectedBalloonId={selectedBalloonId}
            onSelectItem={selectItem}
            onSelectSource={(sourceId) => {
              setSelectedSourceId(sourceId);
              setSelectedBalloonId(undefined);
              const source = sources.find((candidate) => candidate.id === sourceId);
              setPageIndex(source?.pageIndex ?? pageIndex);
            }}
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

        <section
          className="inspection-pane"
          aria-label={zhCN.workbench.reviewRegion}
          role="region"
        >
          <RecognitionSummary
            items={items}
            balloons={balloons}
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
          {workingCopy === undefined ? null : (
            <CoverageReviewPanel
              entries={workingCopy.coverage.entries ?? []}
              sources={sources}
              selectedSourceId={selectedSourceId}
              disabled={pendingCommand !== undefined || busy || reviewImmutable}
              onSelectSource={(sourceId) => {
                setSelectedSourceId(sourceId);
                setSelectedBalloonId(undefined);
                const source = sources.find((candidate) => candidate.id === sourceId);
                setPageIndex(source?.pageIndex ?? pageIndex);
              }}
              onCommand={queueCommand}
            />
          )}
          <InspectionItemTable
            items={items}
            balloons={balloons}
            candidateNumbers={candidateNumbers}
            filter={filter}
            selectedItemId={selectedItemId}
            disabled={pendingCommand !== undefined || busy || reviewImmutable}
            onSelectItem={selectItem}
            onCommand={queueCommand}
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
              disabled={pendingCommand !== undefined || busy || reviewImmutable}
              selectedItemId={selectedItemId}
              onSelectItem={selectItem}
              pageIndex={pageIndex}
              onCommand={queueCommand}
            />
          </details>
        </section>

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
                  disabled={busy || reviewImmutable || pendingCommand !== undefined}
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
                        }}
                      />
                    </label>
                  ))}
                  <button
                    type="button"
                    disabled={Object.values(metadata).some(
                      (value) => value.trim() === "",
                    )}
                    onClick={() => queueCommand({
                      type: "set_sip_metadata",
                      ...metadata,
                    })}
                  >
                    {zhCN.workbench.confirmMetadata}
                  </button>
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
      </div>
    </main>
  );
}
