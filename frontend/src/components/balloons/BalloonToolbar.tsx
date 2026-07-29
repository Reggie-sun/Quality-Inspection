import type { BalloonOverlay } from "../../api/types";
import { zhCN } from "../../copy/zhCN";


type BalloonToolbarProps = {
  balloons: BalloonOverlay[];
  selectedBalloonId?: string;
  disabled?: boolean;
  onDelete: (balloonId: string, expectedVersion: number) => void;
  onRebuild: (balloonId: string, expectedVersion: number) => void;
  onReorder: (balloonId: string, expectedVersion: number, sortOrder: number) => void;
  onRenumber: (orderedIds: string[], expectedVersions: Record<string, number>) => void;
};


export function BalloonToolbar({
  balloons,
  selectedBalloonId,
  disabled = false,
  onDelete,
  onRebuild,
  onReorder,
  onRenumber,
}: BalloonToolbarProps) {
  const selected = balloons.find((balloon) => balloon.id === selectedBalloonId);
  const active = balloons
    .filter((balloon) => balloon.status !== "deleted" && balloon.version !== undefined)
    .sort((left, right) => (left.sortOrder ?? 0) - (right.sortOrder ?? 0));
  const selectedActive =
    selected?.version !== undefined && selected.status !== "deleted"
      ? { balloon: selected, version: selected.version }
      : undefined;
  const selectedDeleted =
    selected?.version !== undefined && selected.status === "deleted"
      ? { balloon: selected, version: selected.version }
      : undefined;

  if (active.length === 0 && selectedDeleted === undefined) return null;

  return (
    <section aria-label={zhCN.balloon.commands} className="balloon-toolbar">
      <div className="balloon-toolbar__heading">
        <h2>{zhCN.balloon.commands}</h2>
        <span>{active.length} {zhCN.balloon.active}</span>
      </div>
      <div className="balloon-toolbar__actions">
        {selectedActive === undefined ? null : (
          <>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onDelete(
                selectedActive.balloon.id,
                selectedActive.version,
              )}
            >
              {zhCN.balloon.delete}
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onRebuild(
                selectedActive.balloon.id,
                selectedActive.version,
              )}
            >
              {zhCN.balloon.rebuild}
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onReorder(
                selectedActive.balloon.id,
                selectedActive.version,
                Math.max(0, (selectedActive.balloon.sortOrder ?? 0) - 1),
              )}
            >
              {zhCN.balloon.earlier}
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onReorder(
                selectedActive.balloon.id,
                selectedActive.version,
                (selectedActive.balloon.sortOrder ?? 0) + 1,
              )}
            >
              {zhCN.balloon.later}
            </button>
          </>
        )}
        {selectedDeleted === undefined ? null : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRebuild(
              selectedDeleted.balloon.id,
              selectedDeleted.version,
            )}
          >
            {zhCN.balloon.rebuild}
          </button>
        )}
        {active.length === 0 ? null : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRenumber(
              active.map((balloon) => balloon.id),
              Object.fromEntries(
                active.map((balloon) => [balloon.id, balloon.version as number]),
              ),
            )}
          >
            {zhCN.balloon.renumber}
          </button>
        )}
      </div>
    </section>
  );
}
