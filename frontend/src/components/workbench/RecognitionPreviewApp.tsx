import { useEffect, useState } from "react";

import { getJson } from "../../api/client";
import type { RecognitionPreview } from "../../api/types";
import { zhCN } from "../../copy/zhCN";


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

  if (!preview) {
    return <main><h1>{zhCN.recognitionPreview.title}</h1></main>;
  }

  const counts = preview.counts;
  return (
    <main aria-label={zhCN.recognitionPreview.title}>
      <h1>{zhCN.recognitionPreview.title}</h1>
      <p>{zhCN.recognitionPreview.version(preview.revision)}</p>
      <p>
        {preview.stage === "vlm_enriching"
          ? zhCN.recognitionPreview.vlmEnriching
          : zhCN.recognitionPreview.localReady}
      </p>
      <iframe
        title={zhCN.recognitionPreview.drawingTitle}
        src={preview.source_pdf_url}
      />
      {preview.semantic_snapshot.candidates.map((candidate) => (
        <p key={candidate.candidate_id}>{candidate.label}</p>
      ))}
      {preview.semantic_snapshot.sources.map((source) => (
        <p key={source.source_location_id}>{source.raw_text}</p>
      ))}
      <p>{zhCN.recognitionPreview.localResolved(counts.local_resolved)}</p>
      <p>{zhCN.recognitionPreview.cacheResolved(counts.cache_resolved)}</p>
      <p>{zhCN.recognitionPreview.vlmPending(counts.vlm_pending)}</p>
    </main>
  );
}
