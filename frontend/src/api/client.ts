import type { GetJson, PostJson } from "./types";


export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}


async function json<Result>(response: Response): Promise<Result> {
  const payload = await response.json() as {
    error?: { code?: string; message?: string };
  } & Result;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload.error?.code ?? "request_failed",
      payload.error?.message ?? `Request failed with status ${response.status}`,
    );
  }
  return payload;
}


export const getJson: GetJson = async <Result>(path: string) => {
  return json<Result>(await fetch(path, { headers: { Accept: "application/json" } }));
};


export const postJson: PostJson = async <Result>(path: string, body: unknown, headers: Record<string, string>) => {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  return json<Result>(response);
};
