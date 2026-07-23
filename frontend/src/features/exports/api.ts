import { downloadPath } from "../../api/client";
import type {
  ExportArtifactKind,
  ExportJob,
  PostJson,
} from "../../api/types";


export function createExport(
  post: PostJson,
  projectId: string,
  reviewedResultId: string,
): Promise<ExportJob> {
  return post(
    `/api/v1/projects/${projectId}/exports`,
    { reviewed_result_id: reviewedResultId },
    {},
  );
}


export function exportDownloadPath(
  exportId: string,
  kind: ExportArtifactKind,
): string {
  return downloadPath(exportId, kind);
}
