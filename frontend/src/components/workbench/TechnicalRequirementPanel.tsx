import {
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Ref } from "react";

import type {
  ReviewCommand,
  ReviewItem,
  TechnicalRequirement,
} from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import type { DraftSaveHandle } from "./draftSave";


type TechnicalRequirementPanelProps = {
  requirements: TechnicalRequirement[];
  items: ReviewItem[];
  disabled?: boolean;
  onSelectItem: (itemId: string) => boolean | void;
  onCommand: (
    command: ReviewCommand,
  ) => boolean | void | Promise<boolean | void>;
  onDraftChange?: (dirty: boolean) => void;
  draftSaveRef?: Ref<DraftSaveHandle>;
};

type DraftMode = "" | "suggested" | "subset" | "global" | "excluded";

type RequirementDraft = {
  mode: DraftMode;
  matchedItemIds: string[];
  search: string;
};

const EMPTY_DRAFT: RequirementDraft = {
  mode: "",
  matchedItemIds: [],
  search: "",
};


function needsConfirmation(requirement: TechnicalRequirement): boolean {
  return (
    requirement.review_required
    && requirement.review_status !== "excluded"
  );
}


function outcomeLabel(requirement: TechnicalRequirement): string {
  if (requirement.review_status === "excluded") {
    return zhCN.technicalRequirements.excluded;
  }
  if (needsConfirmation(requirement)) {
    return zhCN.technicalRequirements.pending;
  }
  if (requirement.review_status === "confirmed") {
    return zhCN.technicalRequirements.confirmed;
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


function editDraft(requirement: TechnicalRequirement): RequirementDraft {
  if (requirement.review_status === "excluded") {
    return { ...EMPTY_DRAFT, mode: "excluded" };
  }
  if (requirement.match_outcome === "global_scope") {
    return { ...EMPTY_DRAFT, mode: "global" };
  }
  if (
    requirement.match_outcome === "matched_items"
    && requirement.matched_candidate_ids.length > 0
  ) {
    return {
      ...EMPTY_DRAFT,
      mode: "suggested",
      matchedItemIds: requirement.matched_candidate_ids,
    };
  }
  return EMPTY_DRAFT;
}


function terminalSummary(requirement: TechnicalRequirement): string {
  if (requirement.review_status === "excluded") {
    return zhCN.technicalRequirements.excludedSummary;
  }
  if (requirement.match_outcome === "global_scope") {
    return zhCN.technicalRequirements.globalSummary;
  }
  return zhCN.technicalRequirements.appliedSummary(
    requirement.matched_candidate_ids.length,
  );
}


function sameDraftDecision(
  left: RequirementDraft,
  right: RequirementDraft,
): boolean {
  return (
    left.mode === right.mode
    && left.matchedItemIds.length === right.matchedItemIds.length
    && left.matchedItemIds.every((itemId, index) =>
      itemId === right.matchedItemIds[index])
  );
}


export function TechnicalRequirementPanel({
  requirements,
  items,
  disabled = false,
  onSelectItem,
  onCommand,
  onDraftChange,
  draftSaveRef,
}: TechnicalRequirementPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [editingRequirementId, setEditingRequirementId] = useState<string>();
  const [draft, setDraft] = useState<RequirementDraft>(EMPTY_DRAFT);
  const [submittedRequirementIds, setSubmittedRequirementIds] = useState<
    string[]
  >([]);
  const [commandBusy, setCommandBusy] = useState(false);
  const previousPendingCount = useRef(0);
  const listId = useId();
  const radioName = useId();
  const activeItems = useMemo(
    () => items.filter((item) => item.active),
    [items],
  );
  const candidateItems = useMemo(
    () => activeItems.filter(
      (item) => item.item_type !== "general_requirement",
    ),
    [activeItems],
  );
  const itemById = useMemo(
    () => new Map(activeItems.map((item) => [item.item_id, item])),
    [activeItems],
  );
  const pendingRequirements = requirements.filter((requirement) =>
    needsConfirmation(requirement));
  const pendingCount = pendingRequirements.length;
  const confirmedCount = requirements.length - pendingCount;
  const firstPending = pendingRequirements.find(
    (requirement) =>
      !submittedRequirementIds.includes(requirement.requirement_id),
  );
  const activeRequirementId = editingRequirementId
    ?? firstPending?.requirement_id;
  const activeRequirement = requirements.find(
    (requirement) => requirement.requirement_id === activeRequirementId,
  );
  useEffect(() => {
    if (activeRequirement === undefined) {
      setDraft(EMPTY_DRAFT);
      return;
    }
    setDraft(
      activeRequirement.requirement_id === editingRequirementId
        ? editDraft(activeRequirement)
        : EMPTY_DRAFT,
    );
  }, [activeRequirement?.requirement_id, editingRequirementId]);

  useEffect(() => {
    setSubmittedRequirementIds((current) => current.filter((requirementId) =>
      pendingRequirements.some(
        (requirement) => requirement.requirement_id === requirementId,
      )));
  }, [requirements]);

  useEffect(() => {
    if (previousPendingCount.current > 0 && pendingCount === 0) {
      setExpanded(false);
      setEditingRequirementId(undefined);
    }
    previousPendingCount.current = pendingCount;
  }, [pendingCount]);

  const selectedMatchedIds = candidateItems
    .filter((item) => draft.matchedItemIds.includes(item.item_id))
    .map((item) => item.item_id);
  const suggestedIds = activeRequirement?.matched_candidate_ids.filter(
    (itemId) => itemById.has(itemId),
  ) ?? [];
  const suggestedAvailable = (
    activeRequirement?.match_outcome === "matched_items"
    && suggestedIds.length > 0
    && suggestedIds.length === activeRequirement.matched_candidate_ids.length
  );
  const globalSuggested = (
    activeRequirement?.match_outcome === "global_scope"
    && activeRequirement.review_status === "suggested"
  );
  const allCandidateItemsSelected = (
    candidateItems.length > 0
    && selectedMatchedIds.length === candidateItems.length
  );
  const draftValid = (
    (draft.mode === "suggested" && suggestedAvailable)
    || (draft.mode === "subset" && selectedMatchedIds.length > 0)
    || draft.mode === "global"
    || draft.mode === "excluded"
  );
  const draftBaseline = (
    activeRequirement !== undefined
    && activeRequirement.requirement_id === editingRequirementId
  )
    ? editDraft(activeRequirement)
    : EMPTY_DRAFT;
  const draftDirty = !sameDraftDecision(draft, draftBaseline);
  const visibleCandidateItems = candidateItems.filter((item) =>
    item.raw_text.toLocaleLowerCase().includes(
      draft.search.trim().toLocaleLowerCase(),
    ));

  const chooseMode = (mode: DraftMode) => {
    setDraft((current) => ({
      mode,
      matchedItemIds: mode === "subset"
        ? current.matchedItemIds
        : mode === "suggested"
          ? suggestedIds
          : [],
      search: mode === "subset" ? current.search : "",
    }));
  };

  const toggleItem = (itemId: string) => {
    setDraft((current) => ({
      ...current,
      matchedItemIds: current.matchedItemIds.includes(itemId)
        ? current.matchedItemIds.filter((candidateId) => candidateId !== itemId)
        : [...current.matchedItemIds, itemId],
    }));
  };

  const cancelDraft = () => {
    if (editingRequirementId !== undefined) {
      setEditingRequirementId(undefined);
    }
    setDraft(EMPTY_DRAFT);
  };

  const submitDraft = async (): Promise<boolean> => {
    if (
      activeRequirement === undefined
      || !draftValid
      || commandBusy
      || disabled
    ) return false;
    let command: ReviewCommand;
    if (draft.mode === "suggested") {
      command = {
        type: "set_technical_requirement_match",
        requirement_id: activeRequirement.requirement_id,
        outcome: "matched_items",
        matched_item_ids: suggestedIds,
      };
    } else if (draft.mode === "subset") {
      command = {
        type: "set_technical_requirement_match",
        requirement_id: activeRequirement.requirement_id,
        outcome: "matched_items",
        matched_item_ids: selectedMatchedIds,
      };
    } else if (draft.mode === "global") {
      command = {
        type: "set_technical_requirement_match",
        requirement_id: activeRequirement.requirement_id,
        outcome: "global_scope",
      };
    } else {
      command = {
        type: "set_technical_requirement_match",
        requirement_id: activeRequirement.requirement_id,
        outcome: "excluded",
      };
    }

    setCommandBusy(true);
    try {
      const succeeded = (await onCommand(command)) !== false;
      if (!succeeded) return false;
      setSubmittedRequirementIds((current) => [
        ...current,
        activeRequirement.requirement_id,
      ]);
      setEditingRequirementId(undefined);
      setDraft(EMPTY_DRAFT);
      return true;
    } finally {
      setCommandBusy(false);
    }
  };

  useEffect(() => {
    onDraftChange?.(draftDirty);
  }, [draftDirty, onDraftChange]);

  useEffect(() => () => {
    onDraftChange?.(false);
  }, [onDraftChange]);

  useImperativeHandle(draftSaveRef, () => ({
    saveDrafts: async () => !draftDirty || await submitDraft(),
  }));

  const impactSummary = draft.mode === "suggested"
    ? zhCN.technicalRequirements.matchedImpact(suggestedIds.length)
    : draft.mode === "subset"
      ? zhCN.technicalRequirements.matchedImpact(selectedMatchedIds.length)
      : draft.mode === "global"
        ? zhCN.technicalRequirements.globalImpact
        : draft.mode === "excluded"
          ? zhCN.technicalRequirements.excludedImpact
          : "";

  if (requirements.length === 0) return null;

  return (
    <section
      className="technical-requirements"
      data-expanded={expanded}
      data-active-editor={activeRequirement !== undefined}
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
          {pendingCount === 0 ? (
            <span className="technical-requirements__confirmed-count">
              {zhCN.technicalRequirements.confirmedCount(confirmedCount)}
            </span>
          ) : (
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
            const isActiveEditor = (
              activeRequirementId === requirement.requirement_id
            );
            const isTerminal = !needsConfirmation(requirement);
            const isEditing = (
              editingRequirementId === requirement.requirement_id
            );
            const isSubmitted = submittedRequirementIds.includes(
              requirement.requirement_id,
            );
            return (
              <li
                key={requirement.requirement_id}
                className="technical-requirement"
                data-state={
                  isActiveEditor
                    ? "editing"
                    : isTerminal
                      ? "terminal"
                      : "waiting"
                }
              >
                <div className="technical-requirement__summary">
                  <span className="technical-requirement__ordinal">
                    {requirement.ordinal ?? "—"}
                  </span>
                  <p>{requirement.raw_text}</p>
                  <span
                    className="technical-requirement__outcome"
                    data-outcome={
                      isTerminal ? requirement.review_status : "pending"
                    }
                  >
                    {outcomeLabel(requirement)}
                  </span>
                </div>

                {isActiveEditor ? (
                  <div className="technical-requirement__editor">
                    <div className="technical-requirement__editor-heading">
                      <strong>
                        {zhCN.technicalRequirements.currentProcessing}
                      </strong>
                      <span>
                        {isEditing
                          ? zhCN.technicalRequirements.editing
                          : zhCN.technicalRequirements.decisionRequired}
                      </span>
                    </div>
                    <fieldset className="technical-requirement__choices">
                      <legend>{zhCN.technicalRequirements.chooseMode}</legend>
                      {suggestedAvailable ? (
                        <label data-selected={draft.mode === "suggested"}>
                          <input
                            type="radio"
                            name={radioName}
                            aria-label={
                              isEditing
                                ? zhCN.technicalRequirements.keepCurrent
                                : zhCN.technicalRequirements.useSuggestion
                            }
                            checked={draft.mode === "suggested"}
                            disabled={disabled || commandBusy}
                            onChange={() => chooseMode("suggested")}
                          />
                          <span>
                            <strong>
                              {isEditing
                                ? zhCN.technicalRequirements.keepCurrent
                                : zhCN.technicalRequirements.useSuggestion}
                            </strong>
                            <small>
                              {isEditing
                                ? zhCN.technicalRequirements.currentTargets(
                                  suggestedIds.length,
                                )
                                : zhCN.technicalRequirements.suggestedTargets(
                                  suggestedIds.length,
                                )}
                            </small>
                          </span>
                        </label>
                      ) : null}
                      <label data-selected={draft.mode === "global"}>
                        <input
                          type="radio"
                          name={radioName}
                          aria-label={zhCN.technicalRequirements.useGlobal}
                          checked={draft.mode === "global"}
                          disabled={disabled || commandBusy}
                          onChange={() => chooseMode("global")}
                        />
                        <span>
                          <strong>
                            {zhCN.technicalRequirements.useGlobal}
                          </strong>
                          <small>
                            {globalSuggested
                              ? zhCN.technicalRequirements.globalSuggestedHint
                              : zhCN.technicalRequirements.globalHint}
                          </small>
                        </span>
                      </label>
                      <label data-selected={draft.mode === "subset"}>
                        <input
                          type="radio"
                          name={radioName}
                          aria-label={zhCN.technicalRequirements.useSubset}
                          checked={draft.mode === "subset"}
                          disabled={disabled || commandBusy}
                          onChange={() => chooseMode("subset")}
                        />
                        <span>
                          <strong>
                            {zhCN.technicalRequirements.useSubset}
                          </strong>
                          <small>
                            {zhCN.technicalRequirements.subsetHint}
                          </small>
                        </span>
                      </label>
                      <label data-selected={draft.mode === "excluded"}>
                        <input
                          type="radio"
                          name={radioName}
                          aria-label={zhCN.technicalRequirements.exclude}
                          checked={draft.mode === "excluded"}
                          disabled={disabled || commandBusy}
                          onChange={() => chooseMode("excluded")}
                        />
                        <span>
                          <strong>
                            {zhCN.technicalRequirements.exclude}
                          </strong>
                          <small>
                            {zhCN.technicalRequirements.excludeHint}
                          </small>
                        </span>
                      </label>
                    </fieldset>

                    {suggestedAvailable ? (
                      <button
                        type="button"
                        className="technical-requirement__view-suggestion"
                        disabled={disabled || commandBusy}
                        onClick={() => onSelectItem(suggestedIds[0])}
                      >
                        {zhCN.technicalRequirements.viewSuggestion(
                          suggestedIds.length,
                        )}
                      </button>
                    ) : null}

                    {draft.mode === "subset" ? (
                      <div className="technical-requirement__picker">
                        <input
                          type="search"
                          aria-label={zhCN.technicalRequirements.searchItems}
                          placeholder={zhCN.technicalRequirements.searchItems}
                          value={draft.search}
                          disabled={disabled || commandBusy}
                          onChange={(event) => setDraft((current) => ({
                            ...current,
                            search: event.target.value,
                          }))}
                        />
                        <p
                          className="technical-requirement__selection-status"
                          role="status"
                        >
                          {allCandidateItemsSelected
                            ? zhCN.technicalRequirements.allCurrentItemsSelected(
                              candidateItems.length,
                            )
                            : zhCN.technicalRequirements.selectedItems(
                              selectedMatchedIds.length,
                              candidateItems.length,
                            )}
                        </p>
                        <div className="technical-requirement__picker-list">
                          {visibleCandidateItems.map((item) => (
                            <label key={item.item_id}>
                              <input
                                type="checkbox"
                                aria-label={item.raw_text}
                                checked={draft.matchedItemIds.includes(
                                  item.item_id,
                                )}
                                disabled={disabled || commandBusy}
                                onChange={() => toggleItem(item.item_id)}
                              />
                              <span>{item.raw_text}</span>
                            </label>
                          ))}
                          {visibleCandidateItems.length === 0 ? (
                            <p>{zhCN.technicalRequirements.noMatchingItems}</p>
                          ) : null}
                        </div>
                      </div>
                    ) : null}

                    {impactSummary === "" ? null : (
                      <div className="technical-requirement__impact">
                        <strong>{zhCN.technicalRequirements.impactTitle}</strong>
                        <p>{impactSummary}</p>
                      </div>
                    )}
                    <div className="technical-requirement__actions">
                      <button
                        type="button"
                        className="technical-requirement__confirm"
                        disabled={disabled || commandBusy || !draftValid}
                        onClick={() => void submitDraft()}
                      >
                        {!draftValid
                          ? zhCN.technicalRequirements.chooseFirst
                          : isEditing
                            ? zhCN.technicalRequirements.confirmEdit
                            : zhCN.technicalRequirements.confirmAndNext}
                      </button>
                      <button
                        type="button"
                        disabled={disabled || commandBusy}
                        onClick={cancelDraft}
                      >
                        {zhCN.technicalRequirements.cancel}
                      </button>
                    </div>
                  </div>
                ) : isTerminal ? (
                  <div className="technical-requirement__terminal">
                    <div>
                      <strong>{terminalSummary(requirement)}</strong>
                      <span>
                        {zhCN.technicalRequirements.sourcePage(
                          requirement.page_index + 1,
                        )}
                      </span>
                    </div>
                    <div className="technical-requirement__actions">
                      {currentTargets.length === 0 ? null : (
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => onSelectItem(
                            currentTargets[0].item_id,
                          )}
                        >
                          {zhCN.technicalRequirements.viewRelations}
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={
                          disabled
                          || (
                            draftDirty
                            && activeRequirementId
                              !== requirement.requirement_id
                          )
                        }
                        onClick={() => {
                          setEditingRequirementId(requirement.requirement_id);
                          setDraft(editDraft(requirement));
                          setExpanded(true);
                        }}
                      >
                        {zhCN.technicalRequirements.modify}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="technical-requirement__waiting">
                    {isSubmitted
                      ? zhCN.technicalRequirements.refreshing
                      : zhCN.technicalRequirements.waiting}
                  </p>
                )}
              </li>
            );
          })}
          {pendingCount === 0 ? (
            <li className="technical-requirements__next-step">
              <strong>{zhCN.technicalRequirements.nextStepTitle}</strong>
              <span>{zhCN.technicalRequirements.nextStepHint}</span>
            </li>
          ) : null}
        </ol>
      ) : null}
    </section>
  );
}
