import { useEffect, useState } from "react";

import type { ProjectStatus } from "../api/types";
import { zhCN } from "../copy/zhCN";
import type { ProjectApi, ProjectListItem } from "../features/projects/api";


type DrawingListScreenProps = {
  entries: ProjectListItem[];
  api: ProjectApi;
  warning?: string;
  onUpload: () => void;
  onOpen: (entry: ProjectListItem) => void;
  loaded?: boolean;
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
  loaded = true,
}: DrawingListScreenProps) {
  const [statuses, setStatuses] = useState<Record<string, DrawingStatus>>({});

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
                      <button
                        type="button"
                        aria-label={zhCN.drawingList.continueDrawing(
                          entry.fileName,
                        )}
                        onClick={() => onOpen(entry)}
                      >
                        {zhCN.drawingList.continue}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
