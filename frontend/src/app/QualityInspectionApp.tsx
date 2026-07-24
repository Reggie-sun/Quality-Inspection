import {
  type ChangeEvent,
  type DragEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError } from "../api/client";
import type { ProcessingStage, ProjectStatus } from "../api/types";
import { ProjectWorkbenchApp } from "../components/workbench/ProjectWorkbenchApp";
import { projectErrorCopy, projectErrorGuidance, zhCN } from "../copy/zhCN";
import { projectApi, type ProjectApi } from "../features/projects/api";
import {
  clearCurrentProjectId,
  getCurrentProjectId,
  getOrCreateLocalOperatorId,
  setCurrentProjectId,
} from "./localContext";


type ProductScreen =
  | { kind: "idle" }
  | { kind: "uploading"; file: File }
  | {
      kind: "processing";
      file?: File;
      projectId: string;
      phase: ProcessingStage;
    }
  | { kind: "fatal"; file?: File; code: string; retryable: boolean }
  | { kind: "ready"; projectId: string };

type QualityInspectionAppProps = {
  api?: ProjectApi;
  pollIntervalMs?: number;
};


function initialScreen(): ProductScreen {
  const projectId = getCurrentProjectId();
  return projectId === undefined
    ? { kind: "idle" }
    : { kind: "processing", projectId, phase: "queued" };
}


function isPdf(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}


function readableSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}


function retryableUploadFailure(caught: unknown): boolean {
  if (!(caught instanceof ApiError)) return true;
  return caught.status === 408 || caught.status === 429 || caught.status >= 500;
}


function activeStage(screen: ProductScreen): number {
  if (screen.kind === "ready") return 2;
  if (screen.kind === "processing" && screen.phase === "preparing_review") return 2;
  if (screen.kind === "processing") return 1;
  return 0;
}


function ProcessRail({ screen }: { screen: ProductScreen }) {
  const active = activeStage(screen);
  return (
    <nav className="product-process" aria-label="检验处理阶段">
      <ol>
        {zhCN.stages.map((stage, index) => {
          const stageState = index < active
            ? "已完成"
            : index === active ? "当前阶段" : "待开始";
          return (
            <li
              className={[
                "product-process__stage",
                index < active ? "is-complete" : "",
                index === active ? "is-current" : "",
              ].filter(Boolean).join(" ")}
              aria-current={index === active ? "step" : undefined}
              aria-label={`${stage}，${stageState}`}
              key={stage}
            >
              <span className="product-process__number" aria-hidden="true">
                {index + 1}
              </span>
              <span>
                <strong>{stage}</strong>
                <small>
                  {["PDF文件上传", "识别检验项", "确认检验项", "调整气泡位置", "生成PDF与SIP"][index]}
                  {" · "}
                  {stageState}
                </small>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}


function ProductHeader({ action }: { action?: ReactNode }) {
  return (
    <header className="product-header">
      <div className="product-brand" aria-label={`${zhCN.brand} ${zhCN.product}`}>
        <strong>{zhCN.brand}</strong>
        <span>{zhCN.product}</span>
      </div>
      {action}
    </header>
  );
}


function statusText(screen: ProductScreen): string | undefined {
  if (screen.kind === "uploading") return zhCN.status.uploading;
  if (screen.kind === "processing") {
    if (screen.phase === "queued") return zhCN.status.queued;
    if (screen.phase === "parsing") return zhCN.status.parsing;
    if (screen.phase === "recognizing") return zhCN.status.recognizing;
    return zhCN.status.preparing;
  }
  return undefined;
}

function processingStage(result: ProjectStatus): ProcessingStage {
  if (result.stage !== undefined && result.stage !== null) return result.stage;
  if (result.phase === "queued") return "queued";
  if (result.phase === "ready_for_review") return "preparing_review";
  return "recognizing";
}


export function QualityInspectionApp({
  api = projectApi,
  pollIntervalMs = 1_500,
}: QualityInspectionAppProps) {
  const [screen, setScreen] = useState<ProductScreen>(initialScreen);
  const [selectedFile, setSelectedFile] = useState<File>();
  const [selectionError, setSelectionError] = useState<string>();
  const [statusError, setStatusError] = useState(false);
  const [retryStatusToken, setRetryStatusToken] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const uploadAbort = useRef<AbortController | undefined>(undefined);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const operatorId = useMemo(() => getOrCreateLocalOperatorId(), []);
  const processingProjectId = screen.kind === "processing"
    ? screen.projectId
    : undefined;

  useEffect(() => () => uploadAbort.current?.abort(), []);

  useEffect(() => {
    if (processingProjectId === undefined) return;
    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();

    const poll = async () => {
      try {
        const result = await api.getProjectStatus(
          processingProjectId,
          controller.signal,
        );
        if (cancelled) return;
        setStatusError(false);
        if (result.phase === "ready_for_review" && result.workbench_ready) {
          setScreen({ kind: "ready", projectId: processingProjectId });
          return;
        }
        if (result.phase === "failed") {
          clearCurrentProjectId();
          setScreen((current) => ({
            kind: "fatal",
            file: current.kind === "processing" ? current.file : undefined,
            code: result.error?.code ?? "project_processing_failed",
            retryable: result.retryable,
          }));
          return;
        }
        setScreen((current) => current.kind === "processing"
          ? {
              ...current,
              phase: processingStage(result),
            }
          : current);
        timer = window.setTimeout(() => void poll(), pollIntervalMs);
      } catch (caught) {
        if (cancelled || (caught instanceof DOMException && caught.name === "AbortError")) {
          return;
        }
        setStatusError(true);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [api, pollIntervalMs, processingProjectId, retryStatusToken]);

  const beginUpload = useCallback(async (file: File) => {
    uploadAbort.current?.abort();
    const controller = new AbortController();
    uploadAbort.current = controller;
    setSelectionError(undefined);
    setStatusError(false);
    setScreen({ kind: "uploading", file });
    try {
      const result = await api.createProject(file, controller.signal);
      if (controller.signal.aborted) return;
      if (result.phase === "failed") {
        clearCurrentProjectId();
        setScreen({
          kind: "fatal",
          file,
          code: result.error?.code ?? "project_intake_failed",
          retryable: result.retryable,
        });
        return;
      }
      if (result.project_id === undefined) {
        setScreen({
          kind: "fatal",
          file,
          code: "project_intake_failed",
          retryable: true,
        });
        return;
      }
      setCurrentProjectId(result.project_id);
      setScreen(result.phase === "ready_for_review" && result.workbench_ready
        ? { kind: "ready", projectId: result.project_id }
        : {
            kind: "processing",
            file,
            projectId: result.project_id,
            phase: processingStage(result),
          });
    } catch (caught) {
      if (controller.signal.aborted) return;
      clearCurrentProjectId();
      setScreen({
        kind: "fatal",
        file,
        code: caught instanceof ApiError ? caught.code : "network_error",
        retryable: retryableUploadFailure(caught),
      });
    } finally {
      if (uploadAbort.current === controller) uploadAbort.current = undefined;
    }
  }, [api]);

  const selectFile = (file: File | undefined) => {
    setSelectionError(undefined);
    if (file === undefined) {
      setSelectedFile(undefined);
      return;
    }
    if (!isPdf(file)) {
      setSelectedFile(undefined);
      setSelectionError(projectErrorCopy("invalid_pdf"));
      return;
    }
    clearCurrentProjectId();
    setStatusError(false);
    setSelectedFile(file);
    setScreen({ kind: "idle" });
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    selectFile(event.target.files?.[0]);
  };
  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragActive(false);
    selectFile(event.dataTransfer.files[0]);
  };
  const reset = () => {
    uploadAbort.current?.abort();
    clearCurrentProjectId();
    setSelectedFile(undefined);
    setSelectionError(undefined);
    setStatusError(false);
    setScreen({ kind: "idle" });
  };
  const openFilePicker = () => {
    if (fileInput.current === null) return;
    fileInput.current.value = "";
    fileInput.current.click();
  };
  const retryProcessing = () => {
    if (screen.kind !== "fatal") return;
    if (!screen.retryable) {
      reset();
      return;
    }
    if (screen.file === undefined) {
      reset();
      return;
    }
    clearCurrentProjectId();
    void beginUpload(screen.file);
  };

  if (screen.kind === "ready") {
    return (
      <div className="ready-shell">
        <ProductHeader action={(
          <button type="button" onClick={reset}>{zhCN.upload.another}</button>
        )} />
        <ProjectWorkbenchApp projectId={screen.projectId} operatorId={operatorId} />
      </div>
    );
  }

  const currentStatus = statusText(screen);
  const busy = !statusError
    && (screen.kind === "uploading" || screen.kind === "processing");
  const shownFile = screen.kind === "uploading"
    ? screen.file
    : screen.kind === "processing" || screen.kind === "fatal"
      ? screen.file ?? selectedFile
      : selectedFile;

  return (
    <main className="product-shell" aria-busy={busy}>
      <ProductHeader />
      <ProcessRail screen={screen} />

      <div className="upload-layout">
        <section className="upload-panel" aria-labelledby="upload-title">
          <header className="upload-panel__heading">
            <p>开始新的检验任务</p>
            <h1 id="upload-title">{zhCN.product}</h1>
            <span>{zhCN.intro}</span>
          </header>

          <label
            className={`pdf-dropzone${dragActive ? " is-dragging" : ""}`}
            onDragEnter={() => setDragActive(true)}
            onDragLeave={() => setDragActive(false)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
          >
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept=".pdf,application/pdf"
              aria-label={zhCN.upload.select}
              disabled={busy}
              onChange={onFileChange}
            />
            <strong>{zhCN.upload.select}</strong>
            <span>{zhCN.upload.empty}</span>
            <small>仅支持 PDF 文件</small>
          </label>

          {shownFile === undefined ? null : (
            <div className="selected-file" aria-label={zhCN.upload.selected}>
              <div>
                <span>{zhCN.upload.selected}</span>
                <strong title={shownFile.name}>{shownFile.name}</strong>
              </div>
              <span>{readableSize(shownFile.size)}</span>
            </div>
          )}

          {selectionError === undefined ? null : (
            <p className="message message--error" role="alert">{selectionError}</p>
          )}
          {screen.kind === "fatal" ? (
            <div className="message message--error" role="alert">
              <strong>{projectErrorCopy(screen.code)}</strong>
              <span>{projectErrorGuidance(screen.code, screen.retryable)}</span>
            </div>
          ) : null}
          {statusError ? (
            <div className="message message--error" role="alert">
              <strong>{projectErrorCopy("project_status_failed")}</strong>
              <span>当前任务已保留，不会重复创建项目。</span>
            </div>
          ) : null}

          {currentStatus === undefined || statusError ? null : (
            <div className="processing-status" role="status" aria-live="polite">
              <span className="processing-status__indicator" aria-hidden="true" />
              <div>
                <strong>{currentStatus}</strong>
                <span>{zhCN.status.hint}</span>
              </div>
            </div>
          )}

          <div className="upload-actions">
            {screen.kind === "fatal" ? (
              screen.retryable ? (
                <>
                  <button className="button button--primary" type="button" onClick={retryProcessing}>
                    {zhCN.upload.retry}
                  </button>
                  <button className="button" type="button" onClick={openFilePicker}>
                    {zhCN.upload.replace}
                  </button>
                </>
              ) : (
                <button className="button button--primary" type="button" onClick={openFilePicker}>
                  {zhCN.upload.replace}
                </button>
              )
            ) : statusError ? (
              <>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => {
                    setStatusError(false);
                    setRetryStatusToken((token) => token + 1);
                  }}
                >
                  {zhCN.upload.retryStatus}
                </button>
                <button className="button" type="button" onClick={openFilePicker}>
                  {zhCN.upload.replace}
                </button>
              </>
            ) : (
              <>
                <button
                  className="button button--primary"
                  type="button"
                  disabled={selectedFile === undefined || busy}
                  onClick={() => {
                    if (selectedFile !== undefined) void beginUpload(selectedFile);
                  }}
                >
                  {zhCN.upload.submit}
                </button>
                {selectedFile === undefined || busy ? null : (
                  <>
                    <button className="button" type="button" onClick={openFilePicker}>
                      {zhCN.upload.replace}
                    </button>
                    <button className="button" type="button" onClick={() => selectFile(undefined)}>
                      {zhCN.upload.remove}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        </section>

        <aside className="upload-guidance" aria-label="上传说明">
          <section>
            <span className="guidance-index">01</span>
            <h2>{zhCN.upload.supportTitle}</h2>
            <p>{zhCN.upload.support}</p>
          </section>
          <section>
            <span className="guidance-index">02</span>
            <h2>{zhCN.upload.safetyTitle}</h2>
            <p>{zhCN.upload.safety}</p>
          </section>
          <section className="guidance-flow">
            <span className="guidance-index">03</span>
            <h2>处理说明</h2>
            <ol>
              <li>校验并解析工程 PDF</li>
              <li>识别检验项与来源位置</li>
              <li>准备人工审核工作台</li>
            </ol>
          </section>
        </aside>
      </div>
    </main>
  );
}
