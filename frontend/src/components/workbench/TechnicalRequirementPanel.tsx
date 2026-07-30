import { useId, useState } from "react";

import type {
  ReviewCommand,
  ReviewItem,
  TechnicalRequirement,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";


type TechnicalRequirementPanelProps = {
  requirements: TechnicalRequirement[];
  items: ReviewItem[];
  disabled?: boolean;
  onSelectItem: (itemId: string) => boolean | void;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
};


function outcomeLabel(requirement: TechnicalRequirement): string {
  if (requirement.review_status === "excluded") {
    return zhCN.technicalRequirements.excluded;
  }
  if (requirement.match_outcome === "matched_items") {
    return zhCN.technicalRequirements.matched(
      requirement.matched_candidate_ids.length,
    );
  }
  if (requirement.match_outcome === "global_scope") {
    return zhCN.technicalRequirements.global;
  }
  return zhCN.technicalRequirements.pending;
}


export function TechnicalRequirementPanel({
  requirements,
  items,
  disabled = false,
  onSelectItem,
  onCommand,
}: TechnicalRequirementPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  if (requirements.length === 0) return null;
  const activeItems = items.filter((item) => item.active);
  const itemById = new Map(activeItems.map((item) => [item.item_id, item]));
  const pendingCount = requirements.filter(
    (requirement) =>
      requirement.match_outcome === "unresolved"
      && requirement.review_status !== "excluded",
  ).length;

  return (
    <section
      className="technical-requirements"
      data-expanded={expanded}
      role="region"
      aria-label={zhCN.technicalRequirements.region}
    >
      <header className="technical-requirements__header">
        <div>
          <h2>{zhCN.technicalRequirements.title}</h2>
          <p>{zhCN.technicalRequirements.hint}</p>
        </div>
        <div className="technical-requirements__meta">
          <span className="technical-requirements__count">
            {zhCN.technicalRequirements.count(requirements.length)}
          </span>
          {pendingCount === 0 ? null : (
            <span className="technical-requirements__pending-count">
              {zhCN.technicalRequirements.pendingCount(pendingCount)}
            </span>
          )}
          <button
            type="button"
            aria-controls={listId}
            aria-expanded={expanded}
            aria-label={
              expanded
                ? zhCN.technicalRequirements.collapseLabel
                : zhCN.technicalRequirements.expandLabel
            }
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded
              ? zhCN.technicalRequirements.collapse
              : zhCN.technicalRequirements.expand}
          </button>
        </div>
      </header>
      {expanded ? (
        <ol id={listId} className="technical-requirements__list">
          {requirements.map((requirement) => {
            const currentTargets = requirement.matched_candidate_ids
              .map((itemId) => itemById.get(itemId))
              .filter((item): item is ReviewItem => item !== undefined);
            const alternativeTargets = activeItems.filter(
              (item) =>
                item.item_type !== "general_requirement"
                && !requirement.matched_candidate_ids.includes(item.item_id),
            );
            return (
              <li
                key={requirement.requirement_id}
                className="technical-requirement"
              >
                <div className="technical-requirement__summary">
                  <span className="technical-requirement__ordinal">
                    {requirement.ordinal ?? "—"}
                  </span>
                  <p>{requirement.raw_text}</p>
                  <span
                    className="technical-requirement__outcome"
                    data-outcome={requirement.match_outcome}
                  >
                    {outcomeLabel(requirement)}
                  </span>
                </div>
                {currentTargets.length === 0 ? null : (
                  <div className="technical-requirement__targets">
                    {currentTargets.map((item) => (
                      <button
                        type="button"
                        key={item.item_id}
                        disabled={disabled}
                        onClick={() => onSelectItem(item.item_id)}
                      >
                        {zhCN.technicalRequirements.viewTarget(item.raw_text)}
                      </button>
                    ))}
                  </div>
                )}
                <details
                  className="technical-requirement__override"
                  open={
                    requirement.match_outcome === "unresolved"
                    && requirement.review_status !== "excluded"
                  }
                >
                  <summary>{zhCN.technicalRequirements.adjustMatch}</summary>
                  <div className="technical-requirement__actions">
                    {alternativeTargets.map((item) => (
                      <button
                        type="button"
                        key={item.item_id}
                        disabled={disabled}
                        onClick={() => onCommand({
                          type: "set_technical_requirement_match",
                          requirement_id: requirement.requirement_id,
                          outcome: "matched_items",
                          matched_item_ids: [item.item_id],
                        })}
                      >
                        {zhCN.technicalRequirements.matchTarget(item.raw_text)}
                      </button>
                    ))}
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onCommand({
                        type: "set_technical_requirement_match",
                        requirement_id: requirement.requirement_id,
                        outcome: "global_scope",
                      })}
                    >
                      {zhCN.technicalRequirements.setGlobal}
                    </button>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onCommand({
                        type: "set_technical_requirement_match",
                        requirement_id: requirement.requirement_id,
                        outcome: "excluded",
                      })}
                    >
                      {zhCN.technicalRequirements.exclude}
                    </button>
                  </div>
                </details>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
