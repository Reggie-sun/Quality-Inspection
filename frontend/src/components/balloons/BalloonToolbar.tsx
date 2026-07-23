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
  const unavailable = disabled || selected?.version === undefined;
  const active = balloons
    .filter((balloon) => balloon.status !== "deleted" && balloon.version !== undefined)
    .sort((left, right) => (left.sortOrder ?? 0) - (right.sortOrder ?? 0));

  return (
    <section aria-label={zhCN.balloon.commands} className="balloon-toolbar">
      <div className="balloon-toolbar__heading">
        <h2>{zhCN.balloon.commands}</h2>
        <span>{active.length} {zhCN.balloon.active}</span>
      </div>
      <div className="balloon-toolbar__actions">
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) onDelete(selected.id, selected.version);
          }}
        >
          {zhCN.balloon.delete}
        </button>
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) onRebuild(selected.id, selected.version);
          }}
        >
          {zhCN.balloon.rebuild}
        </button>
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) {
              onReorder(selected.id, selected.version, Math.max(0, (selected.sortOrder ?? 0) - 1));
            }
          }}
        >
          {zhCN.balloon.earlier}
        </button>
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) {
              onReorder(selected.id, selected.version, (selected.sortOrder ?? 0) + 1);
            }
          }}
        >
          {zhCN.balloon.later}
        </button>
        <button
          type="button"
          disabled={disabled || active.length === 0}
          onClick={() => onRenumber(
            active.map((balloon) => balloon.id),
            Object.fromEntries(
              active.map((balloon) => [balloon.id, balloon.version as number]),
            ),
          )}
        >
          {zhCN.balloon.renumber}
        </button>
      </div>
    </section>
  );
}
