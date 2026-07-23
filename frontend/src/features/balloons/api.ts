import type { BalloonRecord, PostJson } from "../../api/types";


export type BalloonCommand =
  | { type: "move"; balloon_id: string; expected_version: number; center_pdf: [number, number] }
  | { type: "delete"; balloon_id: string; expected_version: number }
  | { type: "rebuild"; balloon_id: string; expected_version: number }
  | { type: "reorder"; balloon_id: string; expected_version: number; sort_order: number }
  | {
      type: "renumber";
      ordered_balloon_ids: string[];
      expected_versions: Record<string, number>;
    };


function operatorHeaders(operatorId: string): Record<string, string> {
  return { "X-QI-Operator": operatorId };
}


export function generateBalloons(
  post: PostJson,
  projectId: string,
  operatorId: string,
  expectedVersion: number,
): Promise<{ balloons: BalloonRecord[] }> {
  return post(
    `/api/v1/projects/${projectId}/balloons/generate`,
    { expected_version: expectedVersion },
    operatorHeaders(operatorId),
  );
}


export function applyBalloonCommand(
  post: PostJson,
  projectId: string,
  operatorId: string,
  command: BalloonCommand,
): Promise<BalloonRecord | { balloons: BalloonRecord[] }> {
  return post(
    `/api/v1/projects/${projectId}/balloons/commands`,
    command,
    operatorHeaders(operatorId),
  );
}
