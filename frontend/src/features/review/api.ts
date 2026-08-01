import type {
  PostJson,
  ReviewedResultResponse,
  ReviewLockResponse,
  ReviewWorkingCopyView,
  ReviewWorkingCopyTransport,
} from "../../api/types";


function operatorHeaders(operatorId: string): Record<string, string> {
  return { "X-QI-Operator": operatorId };
}


export function acquireReviewLock(
  post: PostJson,
  projectId: string,
  operatorId: string,
): Promise<ReviewLockResponse> {
  return post<ReviewLockResponse>(
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
): Promise<ReviewWorkingCopyView> {
  return post<ReviewWorkingCopyTransport>(
    `/api/v1/projects/${projectId}/review/freeze-items`,
    { expected_version: expectedVersion },
    operatorHeaders(operatorId),
  ).then((transport) => transport as unknown as ReviewWorkingCopyView);
}


export function confirmReviewedResult(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
): Promise<ReviewedResultResponse> {
  return post<ReviewedResultResponse>(
    `/api/v1/projects/${projectId}/review/confirm`,
    { expected_version: expectedVersion },
    operatorHeaders(operatorId),
  );
}
