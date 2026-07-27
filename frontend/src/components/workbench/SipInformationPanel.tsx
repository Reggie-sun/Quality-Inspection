import type {
  BalloonOverlay,
  ReviewCommand,
  ReviewItem,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
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
  metadataDirty: boolean;
  disabled: boolean;
  selectedItem?: ReviewItem;
  selectedBalloon?: BalloonOverlay;
  selectedSourceActive?: boolean;
  onMetadataChange: (next: MetadataDraft) => void;
  onConfirmMetadata: () => void;
  onCancelMetadata: () => void;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onSelectedSipDraftChange?: (dirty: boolean) => void;
};


export function SipInformationPanel({
  metadata,
  metadataValues,
  metadataDirty,
  disabled,
  selectedItem,
  selectedBalloon,
  selectedSourceActive = false,
  onMetadataChange,
  onConfirmMetadata,
  onCancelMetadata,
  onCommand,
  onSelectedSipDraftChange,
}: SipInformationPanelProps) {
  const selectedItemActive = selectedItem?.active === true;

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
            ).map(([key, label]) => (
              <label key={key}>
                {label}
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
            ))}
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
        <h3>{zhCN.workbench.selectedSipInformation}</h3>
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
        />
      </section>
    </section>
  );
}
