import { useEffect, useState } from "react";

import { getJson } from "../../api/client";
import type { RecognitionPreview } from "../../api/types";
import { zhCN } from "../../copy/zhCN";
import "../../styles/recognition-preview.css";


type RecognitionPreviewAppProps = {
  projectId: string;
  pollIntervalMs?: number;
};


export function RecognitionPreviewApp({
  projectId,
  pollIntervalMs,
}: RecognitionPreviewAppProps) {
  const [preview, setPreview] = useState<RecognitionPreview>();

  useEffect(() => {
    let active = true;
    setPreview(undefined);
    const path = `/api/v1/projects/${projectId}/recognition-preview`;
    const load = () => getJson<RecognitionPreview>(path)
      .then((value) => {
        if (active) {
          setPreview((current) => (
            current === undefined || value.revision >= current.revision
              ? value
              : current
          ));
        }
      })
      .catch(() => undefined);
    void load();
    const timer = pollIntervalMs === undefined
      ? undefined
      : window.setInterval(() => void load(), pollIntervalMs);
    return () => {
      active = false;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [projectId, pollIntervalMs]);

  return (
    <main
      className="product-shell recognition-preview"
      aria-label={zhCN.recognitionPreview.title}
      aria-busy={preview === undefined}
    >
      <header className="product-header">
        <div className="product-brand" aria-label={`${zhCN.brand} ${zhCN.product}`}>
          <strong>{zhCN.brand}</strong>
          <span>{zhCN.product}</span>
        </div>
        <span className="recognition-preview__readonly">只读识别阶段</span>
      </header>

      {preview === undefined ? (
        <section className="recognition-preview__loading" aria-live="polite">
          <span className="processing-status__indicator" aria-hidden="true" />
          <div>
            <h1>{zhCN.recognitionPreview.title}</h1>
            <p>正在读取本地识别结果…</p>
          </div>
        </section>
      ) : (
        <>
          <section className="recognition-preview__summary" aria-labelledby="recognition-preview-title">
            <div>
              <p className="recognition-preview__eyebrow">处理中预览</p>
              <h1 id="recognition-preview-title">{zhCN.recognitionPreview.title}</h1>
              <p className="recognition-preview__status" aria-live="polite">
                <span className="processing-status__indicator" aria-hidden="true" />
                {preview.stage === "vlm_enriching"
                  ? zhCN.recognitionPreview.vlmEnriching
                  : zhCN.recognitionPreview.localReady}
              </p>
            </div>
            <span className="recognition-preview__version">
              {zhCN.recognitionPreview.version(preview.revision)}
            </span>
            <ul className="recognition-preview__metrics" aria-label="识别进度">
              <li>{zhCN.recognitionPreview.localResolved(preview.counts.local_resolved)}</li>
              <li>{zhCN.recognitionPreview.cacheResolved(preview.counts.cache_resolved)}</li>
              <li>{zhCN.recognitionPreview.vlmPending(preview.counts.vlm_pending)}</li>
            </ul>
          </section>

          <div className="recognition-preview__layout">
            <section
              className="recognition-preview__drawing"
              aria-label={zhCN.recognitionPreview.drawingTitle}
            >
              <header>
                <h2>{zhCN.recognitionPreview.drawingTitle}</h2>
                <span>只读预览</span>
              </header>
              <iframe
                title={zhCN.recognitionPreview.drawingTitle}
                src={preview.source_pdf_url}
              />
            </section>

            <aside className="recognition-preview__results" aria-label="当前识别结果">
              <section>
                <header>
                  <h2>已识别检验项</h2>
                  <span>{preview.semantic_snapshot.candidates.length}</span>
                </header>
                <ul aria-label="已识别检验项">
                  {preview.semantic_snapshot.candidates.length === 0 ? (
                    <li className="recognition-preview__empty">等待识别结果</li>
                  ) : preview.semantic_snapshot.candidates.map((candidate) => (
                    <li key={candidate.candidate_id}>{candidate.label}</li>
                  ))}
                </ul>
              </section>

              <section>
                <header>
                  <h2>识别来源</h2>
                  <span>{preview.semantic_snapshot.sources.length}</span>
                </header>
                <ul aria-label="识别来源">
                  {preview.semantic_snapshot.sources.length === 0 ? (
                    <li className="recognition-preview__empty">等待来源解析</li>
                  ) : preview.semantic_snapshot.sources.map((source) => (
                    <li key={source.source_location_id}>{source.raw_text}</li>
                  ))}
                </ul>
              </section>
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
