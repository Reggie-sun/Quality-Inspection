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
  readyItemCount?: number;
  exceptionItemCount?: number;
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
  readyItemCount = 0,
  exceptionItemCount = 0,
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
  const [inspectionRole, setInspectionRole] = useState("");
  const suggestionByField = new Map(
    metadataSuggestions.map((suggestion) => [suggestion.field, suggestion]),
  );

  return (
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
      <section
        className="sip-selected-information"
        aria-label={zhCN.workbench.selectedSipInformation}
      >
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
        <div className="sip-selected-information__heading">
          <div>
            <h3>{zhCN.workbench.selectedSipInformation}</h3>
            <p>
              {zhCN.workbench.sipTableProgress(
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
        {!selectedItemActive
        || (selectedItem.sip_mapping_exceptions?.length ?? 0) === 0 ? null : (
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
        ) : null}
        <SelectedSipDetailFields
          item={
            !selectedSourceActive && selectedItemActive
              ? selectedItem
              : undefined
          }
          balloon={
            !selectedSourceActive && selectedItemActive
              ? selectedBalloon
              : undefined
          }
          disabled={disabled}
          onCommand={onCommand}
          onDraftChange={onSelectedSipDraftChange}
          onConfirmed={onSelectedSipConfirmed}
          draftSaveRef={selectedSipDraftSaveRef}
        />
      </section>
    </section>
  );
}
