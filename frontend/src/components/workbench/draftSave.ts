export type DraftSaveHandle = {
  saveDrafts: () => Promise<boolean>;
};


export async function saveDraftHandlesInOrder(
  handles: ReadonlyArray<DraftSaveHandle | null>,
): Promise<boolean> {
  for (const handle of handles) {
    if (handle !== null && !(await handle.saveDrafts())) return false;
  }
  return true;
}
