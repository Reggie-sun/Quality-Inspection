import type { BalloonOverlay } from "../../api/types";


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
    <section aria-label="Balloon commands">
      <h2 style={{ margin: "0 0 10px", fontSize: 20 }}>Balloon commands</h2>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) onDelete(selected.id, selected.version);
          }}
        >
          Delete balloon
        </button>
        <button
          type="button"
          disabled={unavailable}
          onClick={() => {
            if (selected?.version !== undefined) onRebuild(selected.id, selected.version);
          }}
        >
          Rebuild balloon
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
          Move balloon earlier
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
          Move balloon later
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
          Renumber balloons
        </button>
      </div>
    </section>
  );
}
