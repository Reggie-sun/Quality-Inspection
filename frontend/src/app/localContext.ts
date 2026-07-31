const LOCAL_OPERATOR_KEY = "qi.local-operator-id";
const CURRENT_PROJECT_KEY = "qi.current-project-id";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;


export function isUuid(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && UUID_PATTERN.test(value);
}


function generateUuid(): string {
  if (typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    value.slice(0, 8),
    value.slice(8, 12),
    value.slice(12, 16),
    value.slice(16, 20),
    value.slice(20),
  ].join("-");
}


export function getOrCreateLocalOperatorId(
  storage: Storage = window.localStorage,
): string {
  const existing = storage.getItem(LOCAL_OPERATOR_KEY);
  if (isUuid(existing)) return existing;
  const generated = generateUuid();
  storage.setItem(LOCAL_OPERATOR_KEY, generated);
  return generated;
}


export function getCurrentProjectId(
  storage: Storage = window.sessionStorage,
): string | undefined {
  const existing = storage.getItem(CURRENT_PROJECT_KEY);
  if (isUuid(existing)) return existing;
  if (existing !== null) storage.removeItem(CURRENT_PROJECT_KEY);
  return undefined;
}


export function setCurrentProjectId(
  projectId: string,
  storage: Storage = window.sessionStorage,
): void {
  if (!isUuid(projectId)) {
    throw new Error("invalid project context");
  }
  storage.setItem(CURRENT_PROJECT_KEY, projectId);
}


export function clearCurrentProjectId(
  storage: Storage = window.sessionStorage,
): void {
  storage.removeItem(CURRENT_PROJECT_KEY);
}
