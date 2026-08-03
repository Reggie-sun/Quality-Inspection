import type { DeleteEmpty, GetJson, PostForm, PostJson } from "./types";


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


export const getJson: GetJson = async <Result>(
  path: string,
  signal?: AbortSignal,
) => {
  const request: RequestInit = { headers: { Accept: "application/json" } };
  if (signal !== undefined) request.signal = signal;
  return json<Result>(await fetch(path, request));
};


export const postJson: PostJson = async <Result>(
  path: string,
  body: unknown,
  headers: Record<string, string>,
  signal?: AbortSignal,
) => {
  const request: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  };
  if (signal !== undefined) request.signal = signal;
  return json<Result>(await fetch(path, request));
};

export const postForm: PostForm = async <Result>(
  path: string,
  body: FormData,
  signal?: AbortSignal,
) => {
  const request: RequestInit = { method: "POST", body };
  if (signal !== undefined) request.signal = signal;
  return json<Result>(await fetch(path, request));
};


export const deleteEmpty: DeleteEmpty = async (
  path: string,
  signal?: AbortSignal,
) => {
  const request: RequestInit = {
    method: "DELETE",
    headers: { Accept: "application/json" },
  };
  if (signal !== undefined) request.signal = signal;
  const response = await fetch(path, request);
  if (!response.ok) await json<never>(response);
};


export function downloadPath(exportId: string, kind: string): string {
  return `/api/v1/exports/${encodeURIComponent(exportId)}/downloads/${encodeURIComponent(kind)}`;
}
