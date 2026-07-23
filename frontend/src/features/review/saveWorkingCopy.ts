import type {
  PostJson,
  ReviewCommand,
  ReviewWorkingCopy,
} from "../../api/types";


export function saveWorkingCopy(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
  command: ReviewCommand,
): Promise<ReviewWorkingCopy> {
  return post<ReviewWorkingCopy>(
    `/api/v1/projects/${projectId}/review/commands`,
    { expected_version: expectedVersion, command },
    { "X-QI-Operator": operatorId },
  );
}
