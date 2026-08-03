import { useEffect, useRef, useState } from "react";

import type { ProjectStatus } from "../api/types";
import { zhCN } from "../copy/zhCN";
import type { ProjectApi, ProjectListItem } from "../features/projects/api";


type DrawingListScreenProps = {
  entries: ProjectListItem[];
  api: ProjectApi;
  warning?: string;
  onUpload: () => void;
  onOpen: (entry: ProjectListItem) => void;
  onReprocess: (entry: ProjectListItem) => Promise<void>;
  onDelete: (entry: ProjectListItem) => Promise<void>;
  loaded?: boolean;
};

type LifecycleAction = {
  kind: "reprocess" | "delete";
  entry: ProjectListItem;
};

type DrawingStatus =
  | { kind: "loading" }
  | { kind: "loaded"; value: ProjectStatus }
  | { kind: "unavailable" };


function statusCopy(status: DrawingStatus): string {
  if (status.kind === "loading") return zhCN.drawingList.loadingStatus;
  if (status.kind === "unavailable") return zhCN.drawingList.unavailableStatus;
  if (
    status.value.phase === "ready_for_review"
    || status.value.phase === "partial_review_required"
  ) {
    return zhCN.drawingList.readyStatus;
  }
  if (status.value.phase === "failed") return zhCN.drawingList.failedStatus;
  if (status.value.stage === "parsing") return zhCN.status.parsing;
  if (status.value.stage === "recognizing") return zhCN.status.recognizing;
  if (status.value.stage === "preparing_review") return zhCN.status.preparing;
  return zhCN.drawingList.queuedStatus;
}


function readableDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


export function DrawingListScreen({
  entries,
  api,
  warning,
  onUpload,
  onOpen,
  onReprocess,
  onDelete,
  loaded = true,
}: DrawingListScreenProps) {
  const [statuses, setStatuses] = useState<Record<string, DrawingStatus>>({});
  const [openMenuProjectId, setOpenMenuProjectId] = useState<string>();
  const [action, setAction] = useState<LifecycleAction>();
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string>();
  const actionTriggerRef = useRef<HTMLButtonElement | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const moreButtonRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    const controllers = entries.map((entry) => {
      const controller = new AbortController();
      setStatuses((current) => ({
        ...current,
        [entry.projectId]: { kind: "loading" },
      }));
      void api.getProjectStatus(entry.projectId, controller.signal)
        .then((value) => {
          if (controller.signal.aborted) return;
          setStatuses((current) => ({
            ...current,
            [entry.projectId]: { kind: "loaded", value },
          }));
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setStatuses((current) => ({
            ...current,
            [entry.projectId]: { kind: "unavailable" },
          }));
        });
      return controller;
    });
    return () => {
      for (const controller of controllers) controller.abort();
    };
  }, [api, entries]);

  useEffect(() => {
    if (openMenuProjectId === undefined) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest("[data-drawing-actions]") === null) {
        setOpenMenuProjectId(undefined);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenuProjectId(undefined);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [openMenuProjectId]);

  useEffect(() => {
    if (action === undefined) return;
    cancelButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || actionPending) return;
      setAction(undefined);
      setActionError(undefined);
      actionTriggerRef.current?.focus();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [action, actionPending]);

  const chooseAction = (
    kind: LifecycleAction["kind"],
    entry: ProjectListItem,
  ) => {
    actionTriggerRef.current = moreButtonRefs.current[entry.projectId];
    setOpenMenuProjectId(undefined);
    setAction({ kind, entry });
    setActionError(undefined);
  };

  const closeDialog = () => {
    if (actionPending) return;
    setAction(undefined);
    setActionError(undefined);
    actionTriggerRef.current?.focus();
  };

  const confirmAction = async () => {
    if (action === undefined || actionPending) return;
    setActionPending(true);
    setActionError(undefined);
    try {
      if (action.kind === "reprocess") await onReprocess(action.entry);
      else await onDelete(action.entry);
      setAction(undefined);
    } catch {
      setActionError(zhCN.drawingList.actionFailed);
    } finally {
      setActionPending(false);
    }
  };

  return (
    <main className="drawing-list-shell">
      <header className="product-header">
        <div
          className="product-brand"
          aria-label={`${zhCN.brand} ${zhCN.product}`}
        >
          <strong>{zhCN.brand}</strong>
          <span>{zhCN.product}</span>
        </div>
        <button
          className="button button--primary"
          type="button"
          onClick={onUpload}
        >
          {zhCN.drawingList.upload}
        </button>
      </header>

      <section className="drawing-list-panel" aria-labelledby="drawing-list-title">
        <header className="drawing-list-panel__heading">
          <div>
            <p>{zhCN.drawingList.eyebrow}</p>
            <h1 id="drawing-list-title">{zhCN.drawingList.title}</h1>
            <span>{zhCN.drawingList.description}</span>
          </div>
          <strong>
            {loaded ? zhCN.drawingList.total(entries.length) : "图纸列表加载中"}
          </strong>
        </header>

        {warning === undefined ? null : (
          <p className="message message--warning" role="status">{warning}</p>
        )}
        {!loaded ? null : entries.length === 0 ? (
          <div className="drawing-list-empty">
            <strong>{zhCN.drawingList.empty}</strong>
            <span>{zhCN.drawingList.emptyHint}</span>
            <button
              className="button button--primary"
              type="button"
              onClick={onUpload}
            >
              {zhCN.drawingList.upload}
            </button>
          </div>
        ) : (
          <div className="drawing-list-table-wrap">
            <table className="drawing-list-table">
              <thead>
                <tr>
                  <th scope="col">{zhCN.drawingList.fileName}</th>
                  <th scope="col">{zhCN.drawingList.status}</th>
                  <th scope="col">{zhCN.drawingList.lastOpened}</th>
                  <th scope="col">{zhCN.drawingList.action}</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.projectId}>
                    <td>
                      <strong title={entry.fileName}>{entry.fileName}</strong>
                    </td>
                    <td>
                      <span className="drawing-list-status" role="status">
                        {statusCopy(
                          statuses[entry.projectId] ?? { kind: "loading" },
                        )}
                      </span>
                    </td>
                    <td>{readableDate(entry.lastOpenedAt)}</td>
                    <td>
                      <div className="drawing-list-actions" data-drawing-actions>
                        <button
                          className="drawing-list-actions__button"
                          type="button"
                          aria-label={zhCN.drawingList.continueDrawing(
                            entry.fileName,
                          )}
                          onClick={() => onOpen(entry)}
                        >
                          {zhCN.drawingList.continue}
                        </button>
                        <div className="drawing-list-actions__menu-anchor">
                          <button
                            className={
                              "drawing-list-actions__button drawing-list-actions__more"
                            }
                            type="button"
                            ref={(button) => {
                              moreButtonRefs.current[entry.projectId] = button;
                            }}
                            aria-label={zhCN.drawingList.moreActions(entry.fileName)}
                            aria-haspopup="menu"
                            aria-expanded={openMenuProjectId === entry.projectId}
                            onClick={() => setOpenMenuProjectId((current) =>
                              current === entry.projectId
                                ? undefined
                                : entry.projectId)}
                          >
                            ⋯
                          </button>
                          {openMenuProjectId !== entry.projectId ? null : (
                            <div className="drawing-list-actions__menu" role="menu">
                              <button
                                type="button"
                                role="menuitem"
                                onClick={() => chooseAction("reprocess", entry)}
                              >
                                {zhCN.drawingList.reprocess}
                              </button>
                              <button
                                className="drawing-list-actions__danger"
                                type="button"
                                role="menuitem"
                                onClick={() => chooseAction("delete", entry)}
                              >
                                {zhCN.drawingList.delete}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {action === undefined ? null : (
        <div
          className="drawing-action-dialog-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDialog();
          }}
        >
          <section
            className="drawing-action-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="drawing-action-dialog-title"
          >
            <h2 id="drawing-action-dialog-title">
              {action.kind === "reprocess"
                ? zhCN.drawingList.reprocessTitle(action.entry.fileName)
                : zhCN.drawingList.deleteTitle(action.entry.fileName)}
            </h2>
            <p>
              {action.kind === "reprocess"
                ? zhCN.drawingList.reprocessDescription
                : zhCN.drawingList.deleteDescription}
            </p>
            {actionError === undefined ? null : (
              <p className="message message--error" role="alert">{actionError}</p>
            )}
            <div className="drawing-action-dialog__actions">
              <button
                ref={cancelButtonRef}
                type="button"
                disabled={actionPending}
                onClick={closeDialog}
              >
                {zhCN.drawingList.cancel}
              </button>
              <button
                className={action.kind === "delete"
                  ? "button drawing-action-dialog__danger"
                  : "button button--primary"}
                type="button"
                disabled={actionPending}
                onClick={() => void confirmAction()}
              >
                {actionPending
                  ? zhCN.drawingList.submitting
                  : action.kind === "reprocess"
                    ? zhCN.drawingList.confirmReprocess
                    : zhCN.drawingList.confirmDelete}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
