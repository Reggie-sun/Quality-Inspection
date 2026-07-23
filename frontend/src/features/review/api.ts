import type { PostJson, ReviewWorkingCopy } from "../../api/types";


function operatorHeaders(operatorId: string): Record<string, string> {
  return { "X-QI-Operator": operatorId };
}


export function acquireReviewLock(
  post: PostJson,
  projectId: string,
  operatorId: string,
): Promise<{ project_id: string; operator_id: string; expires_at?: string }> {
  return post(
    `/api/v1/projects/${projectId}/review/lock`,
    { ttl_seconds: 300 },
    operatorHeaders(operatorId),
  );
}


export function freezeReviewItems(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
): Promise<ReviewWorkingCopy> {
  return post(
    `/api/v1/projects/${projectId}/review/freeze-items`,
    { expected_version: expectedVersion },
    operatorHeaders(operatorId),
  );
}


export function confirmReviewedResult(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
): Promise<{ id: string }> {
  return post(
    `/api/v1/projects/${projectId}/review/confirm`,
    { expected_version: expectedVersion },
    operatorHeaders(operatorId),
  );
}
