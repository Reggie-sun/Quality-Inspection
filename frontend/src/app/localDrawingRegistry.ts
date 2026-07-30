export type LocalDrawingEntry = {
  projectId: string;
  fileName: string;
  createdAt: string;
  lastOpenedAt: string;
};


export const LOCAL_DRAWING_REGISTRY_KEY = "qi.drawing-list.v1";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const UNKNOWN_DRAWING_NAME = "未命名图纸.pdf";


function validDate(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}


function validEntry(value: unknown): value is LocalDrawingEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.projectId === "string"
    && UUID_PATTERN.test(entry.projectId)
    && typeof entry.fileName === "string"
    && entry.fileName.trim() !== ""
    && validDate(entry.createdAt)
    && validDate(entry.lastOpenedAt)
  );
}


function validWrite(
  projectId: string,
  fileName: string,
  now: Date,
): boolean {
  return (
    UUID_PATTERN.test(projectId)
    && fileName.trim() !== ""
    && !Number.isNaN(now.getTime())
  );
}


function writeLocalDrawings(
  entries: LocalDrawingEntry[],
  storage: Storage,
): boolean {
  try {
    storage.setItem(LOCAL_DRAWING_REGISTRY_KEY, JSON.stringify(entries));
    return true;
  } catch {
    return false;
  }
}


export function readLocalDrawings(
  storage: Storage = window.localStorage,
): LocalDrawingEntry[] {
  try {
    const raw = storage.getItem(LOCAL_DRAWING_REGISTRY_KEY);
    if (raw === null) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    const drawings = new Map<string, LocalDrawingEntry>();
    for (const candidate of parsed) {
      if (!validEntry(candidate)) continue;
      const existing = drawings.get(candidate.projectId);
      if (
        existing === undefined
        || Date.parse(candidate.lastOpenedAt) >= Date.parse(existing.lastOpenedAt)
      ) {
        drawings.set(candidate.projectId, candidate);
      }
    }
    return [...drawings.values()].sort(
      (left, right) =>
        Date.parse(right.lastOpenedAt) - Date.parse(left.lastOpenedAt),
    );
  } catch {
    return [];
  }
}


export function registerLocalDrawing(
  projectId: string,
  fileName: string,
  now: Date = new Date(),
  storage: Storage = window.localStorage,
): boolean {
  if (!validWrite(projectId, fileName, now)) return false;
  const timestamp = now.toISOString();
  const entries = readLocalDrawings(storage);
  const existing = entries.find((entry) => entry.projectId === projectId);
  const nextEntry: LocalDrawingEntry = {
    projectId,
    fileName: fileName.trim(),
    createdAt: existing?.createdAt ?? timestamp,
    lastOpenedAt: timestamp,
  };
  return writeLocalDrawings(
    [
      nextEntry,
      ...entries.filter((entry) => entry.projectId !== projectId),
    ],
    storage,
  );
}


export function touchLocalDrawing(
  projectId: string,
  fallbackFileName = UNKNOWN_DRAWING_NAME,
  now: Date = new Date(),
  storage: Storage = window.localStorage,
): boolean {
  if (!validWrite(projectId, fallbackFileName, now)) return false;
  const existing = readLocalDrawings(storage).find(
    (entry) => entry.projectId === projectId,
  );
  return registerLocalDrawing(
    projectId,
    existing?.fileName ?? fallbackFileName,
    now,
    storage,
  );
}
