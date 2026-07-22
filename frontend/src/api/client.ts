import type { PostJson } from "./types";


export const postJson: PostJson = async (path, body, headers) => {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return payload;
};
