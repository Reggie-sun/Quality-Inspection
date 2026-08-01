import type {
  BalloonOverlay,
  ProjectWorkbenchSipMetadataSuggestion,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { useState, type Ref } from "react";
import { zhCN } from "../../copy/zhCN";
import type { DraftSaveHandle } from "./draftSave";
import { SelectedSipDetailFields } from "./SelectedSipDetailFields";


export type MetadataDraft = {
  material_code: string;
  material_name: string;
  drawing_number: string;
  material: string;
  revision: string;
};

export type SipInformationPanelProps = {
  metadata: MetadataDraft;
  metadataValues: ReadonlyArray<readonly [string, string?]>;
  persistedMetadata?: Partial<MetadataDraft>;
  metadataSuggestions?: ProjectWorkbenchSipMetadataSuggestion[];
  metadataDirty: boolean;
  disabled: boolean;
  selectedItem?: ReviewItem;
  selectedBalloon?: BalloonOverlay;
  selectedSourceActive?: boolean;
  pendingItemCount?: number;
  readyItemCount?: number;
  exceptionItemCount?: number;
  regenerationRequired?: boolean;
  onMetadataChange: (next: MetadataDraft) => void;
  onConfirmMetadata: () => void;
  onCancelMetadata: () => void;
  onSelectNextException?: () => void;
  onSelectedSipConfirmed?: (itemId: string) => void;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onSelectedSipDraftChange?: (dirty: boolean) => void;
  selectedSipDraftSaveRef?: Ref<DraftSaveHandle>;
};


export function SipInformationPanel({
  metadata,
  metadataValues,
  persistedMetadata = {},
  metadataSuggestions = [],
  metadataDirty,
  disabled,
  selectedItem,
  selectedBalloon,
  selectedSourceActive = false,
  pendingItemCount = 0,
  readyItemCount = 0,
  exceptionItemCount = 0,
  regenerationRequired = false,
  onMetadataChange,
  onConfirmMetadata,
  onCancelMetadata,
  onSelectNextException,
  onSelectedSipConfirmed,
  onCommand,
  onSelectedSipDraftChange,
  selectedSipDraftSaveRef,
}: SipInformationPanelProps) {
  const selectedItemActive = selectedItem?.active === true;
  const selectedItemHasException = selectedItemActive
    && (selectedItem.sip_mapping_exceptions?.length ?? 0) > 0;
  const selectedItemRequiresRegeneration = selectedItemHasException
    && selectedItem.sip_mapping_exceptions!.includes(
      "sip_regeneration_required",
    );
  const selectedItemHasEditableException = selectedItemHasException
    && !selectedItemRequiresRegeneration
    && selectedItem.sip_mapping_exceptions!.some(
      (exception) => exception !== "sip_regeneration_required",
    );
  const selectedItemPending = selectedItemActive
    && !selectedItemHasException
    && selectedItem.sip_detail_fields_confirmed !== true;
  const itemCount = pendingItemCount + readyItemCount + exceptionItemCount;
  const sipTableComplete =
    itemCount > 0 && pendingItemCount === 0 && exceptionItemCount === 0;
  const showGeneration =
    pendingItemCount > 0 || itemCount === 0 || regenerationRequired;
  const [inspectionRole, setInspectionRole] = useState("");
  const [manualEditorItemId, setManualEditorItemId] = useState<string>();
  const suggestionByField = new Map(
    metadataSuggestions.map((suggestion) => [suggestion.field, suggestion]),
  );

  return (
    <>
      <section
        className="sip-information-panel"
        role="region"
        aria-label={zhCN.workbench.sipInformation}
      >
        <h2>{zhCN.workbench.sipInformation}</h2>
        <section
          className="sip-project-information"
          aria-label={zhCN.workbench.projectSipInformation}
        >
          <h3>{zhCN.workbench.projectSipInformation}</h3>
          <dl className="sip-metadata-summary">
            {metadataValues.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd title={value}>{value || zhCN.workbench.unknown}</dd>
              </div>
            ))}
          </dl>
          <details className="sip-metadata-editor">
            <summary>{zhCN.workbench.editProjectSipInformation}</summary>
            <fieldset disabled={disabled}>
              <legend className="visually-hidden">
                {zhCN.workbench.editProjectSipInformation}
              </legend>
              {(
                [
                  ["material_code", zhCN.workbench.metadataFields.materialCode],
                  ["material_name", zhCN.workbench.metadataFields.materialName],
                  ["drawing_number", zhCN.workbench.metadataFields.drawingNumber],
                  ["revision", zhCN.workbench.metadataFields.revision],
                  ["material", zhCN.workbench.metadataFields.material],
                ] as const
              ).map(([key, label]) => {
                const suggestion = suggestionByField.get(key);
                const persisted = persistedMetadata[key]?.trim() ?? "";
                const suggested = suggestion?.value.trim() ?? "";
                const metadataConflict =
                  persisted !== "" && suggested !== "" && persisted !== suggested;
                return (
                  <div className="sip-metadata-editor__field" key={key}>
                    <label>
                      <span className="sip-metadata-field-label">
                        {label}
                        {suggested !== "" && persisted === "" ? (
                          <small>{zhCN.workbench.recognizedMetadataSuggestion}</small>
                        ) : suggested !== "" && persisted === suggested ? (
                          <small>{zhCN.workbench.recognizedMetadataConsistent}</small>
                        ) : null}
                      </span>
                      <input
                        aria-label={label}
                        value={metadata[key]}
                        placeholder={zhCN.workbench.unknown}
                        onChange={(event) => {
                          onMetadataChange({
                            ...metadata,
                            [key]: event.target.value,
                          });
                        }}
                      />
                    </label>
                    {metadataConflict ? (
                      <div className="sip-metadata-conflict">
                        <span>{zhCN.workbench.currentMetadataValue(persisted)}</span>
                        <span>{zhCN.workbench.recognizedMetadataValue(suggested)}</span>
                        <button
                          type="button"
                          aria-label={zhCN.workbench.adoptRecognizedMetadata(label)}
                          onClick={() => {
                            onMetadataChange({
                              ...metadata,
                              [key]: suggested,
                            });
                          }}
                        >
                          {zhCN.workbench.adoptRecognizedMetadata(label)}
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
              <div className="sip-metadata-actions">
                <button
                  type="button"
                  disabled={Object.values(metadata).some(
                    (value) => value.trim() === "",
                  )}
                  onClick={onConfirmMetadata}
                >
                  {zhCN.workbench.confirmProjectSipInformation}
                </button>
                <button
                  type="button"
                  disabled={!metadataDirty}
                  onClick={onCancelMetadata}
                >
                  {zhCN.workbench.cancelProjectSipInformation}
                </button>
              </div>
            </fieldset>
          </details>
        </section>
      </section>
      <section
        className="sip-selected-information"
        aria-label={zhCN.workbench.selectedSipInformation}
      >
        {sipTableComplete ? (
          <div
            className="sip-table-complete"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <strong>{zhCN.workbench.sipTableComplete}</strong>
            <span>{zhCN.workbench.sipTableCompleteNextStep}</span>
          </div>
        ) : showGeneration ? (
          <div className="sip-table-generation">
            <label>
              {zhCN.workbench.defaultInspectionRole}
              <input
                aria-label={zhCN.workbench.defaultInspectionRole}
                value={inspectionRole}
                onChange={(event) => setInspectionRole(event.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={disabled || inspectionRole.trim() === ""}
              onClick={() => {
                void onCommand({
                  type: "generate_sip_table",
                  inspection_role: inspectionRole.trim(),
                });
              }}
            >
              {zhCN.workbench.generateSipTable}
            </button>
          </div>
        ) : null}
        <div className="sip-selected-information__heading">
          <div>
            <h3>{zhCN.workbench.selectedSipInformation}</h3>
            <p>
              {pendingItemCount > 0
                ? zhCN.workbench.sipTablePendingProgress(pendingItemCount)
                : zhCN.workbench.sipTableProgress(
                    readyItemCount,
                    exceptionItemCount,
                  )}
            </p>
          </div>
          {exceptionItemCount === 0
          || onSelectNextException === undefined ? null : (
            <button
              type="button"
              disabled={disabled}
              onClick={onSelectNextException}
            >
              {zhCN.workbench.nextSipException}
            </button>
          )}
        </div>
        {!selectedItemHasException ? null : (
          <ul className="sip-mapping-exceptions" aria-label="当前 SIP 异常">
            {selectedItem.sip_mapping_exceptions!.map((exception) => (
              <li key={exception}>
                {zhCN.workbench.sipMappingExceptions[
                  exception as keyof typeof zhCN.workbench.sipMappingExceptions
                ] ?? exception}
              </li>
            ))}
          </ul>
        )}
        {selectedSourceActive ? (
          <p className="sip-information-panel__empty">
            {zhCN.workbench.selectedSourceSipUnavailable}
          </p>
        ) : !selectedItemActive ? (
          <p className="sip-information-panel__empty">
            {zhCN.workbench.selectItemForSip}
          </p>
        ) : selectedItemPending ? (
          <p className="sip-information-panel__empty">
            {zhCN.workbench.pendingSipGeneration}
          </p>
        ) : selectedItemHasException ? null : (
          <div className="sip-resolved-row">
            <div className="sip-resolved-row__status" role="status">
              <strong>{zhCN.workbench.resolvedSipRowComplete}</strong>
              {exceptionItemCount > 0 ? (
                <span>
                  {zhCN.workbench.resolvedSipRowOtherExceptions(
                    exceptionItemCount,
                  )}
                </span>
              ) : null}
            </div>
            {manualEditorItemId === selectedItem.item_id ? (
              <p className="sip-resolved-row__edit-hint">
                {zhCN.workbench.optionalResolvedSipEdit}
              </p>
            ) : (
              <button
                type="button"
                disabled={disabled}
                onClick={() => setManualEditorItemId(selectedItem.item_id)}
              >
                {zhCN.workbench.editResolvedSipRow}
              </button>
            )}
          </div>
        )}
        {selectedItemRequiresRegeneration ? null : (
          <div hidden={
            selectedSourceActive
            || !selectedItemActive
            || selectedItemPending
            || (
              selectedItemHasException
              && !selectedItemHasEditableException
            )
            || (
              !selectedItemHasException
              && manualEditorItemId !== selectedItem.item_id
            )
          }>
            <SelectedSipDetailFields
              item={selectedItemActive ? selectedItem : undefined}
              balloon={selectedBalloon}
              disabled={disabled}
              onCommand={onCommand}
              onDraftChange={onSelectedSipDraftChange}
              onConfirmed={onSelectedSipConfirmed}
              draftSaveRef={selectedSipDraftSaveRef}
            />
          </div>
        )}
      </section>
    </>
  );
}
