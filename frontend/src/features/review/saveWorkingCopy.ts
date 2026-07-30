import type {
  PostJson,
  ReviewCommand,
  ReviewWorkingCopyView,
  ReviewWorkingCopyTransport,
} from "../../api/types";


export function saveWorkingCopy(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
  command: ReviewCommand,
): Promise<ReviewWorkingCopyView> {
  return post<ReviewWorkingCopyTransport>(
    `/api/v1/projects/${projectId}/review/commands`,
    { expected_version: expectedVersion, command },
    { "X-QI-Operator": operatorId },
  ).then((transport) => transport as ReviewWorkingCopyView);
}
