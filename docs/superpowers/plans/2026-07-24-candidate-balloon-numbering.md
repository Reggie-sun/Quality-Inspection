# Candidate Balloon Numbering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让真实 PDF 在识别完成、正式气泡尚未生成时立即显示蓝色候选序号，并在正式气泡生成后由 backend 正式编号无重复地接管。

**Architecture:** 从 `ReviewWorkingCopy.items` 的有效项顺序派生一个只读 `item_id → positive integer` 映射，并把同一映射传给 PDF overlay、检验项列表和选中项摘要。候选序号只存在于 frontend view model；存在 active `BalloonRecord` 时隐藏对应候选标记，正式气泡与正式导出路径保持不变。

**Tech Stack:** React 19、TypeScript、SVG、CSS custom properties、Vitest、Testing Library、Playwright/Chrome。

---

## Execution Contract

- Selected lane: `Standard`
- Selected plan: `docs/superpowers/plans/2026-07-24-candidate-balloon-numbering.md`
- Design source: `docs/superpowers/specs/2026-07-24-candidate-balloon-numbering-design.md`
- Execution location: `/home/reggie/vscode_folder/Quality_Inspection` on `main`, explicitly authorized by the user.
- Single writer: implementation worker only; reviewers are read-only.
- Formal Owner unchanged: backend `BalloonRecord.formal_number`, freeze gate, balloon geometry/collision validation and reviewed-result export.
- Runtime truth: `http://127.0.0.1:4173/` bind-mounts `/home/reggie/vscode_folder/Quality_Inspection/frontend`.
- Rollback: revert the Task 6 implementation commit; first check is the full frontend Vitest suite.

## Allowed Paths

- Create: `frontend/src/components/workbench/candidateNumbering.ts`
- Create: `frontend/src/components/workbench/candidateNumbering.test.ts`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/copy/zhCN.ts`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.tsx`
- Modify: `frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx`
- Modify: `frontend/src/components/workbench/InspectionWorkbench.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.tsx`
- Modify: `frontend/src/components/workbench/InspectionItemTable.test.tsx`
- Modify: `frontend/src/components/pdf/OverlayLayer.tsx`
- Modify: `frontend/src/components/pdf/OverlayLayer.test.tsx`
- Modify: `frontend/src/styles/workbench.css`
- Modify: `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`

Do not modify backend files, `compose.yaml`, dependency manifests, contract matrix, predecessor plans, receipts, Harness runs, credentials, source PDFs or generated exports.

## File Responsibilities

- `candidateNumbering.ts`: one pure function owns derivation of provisional numbers.
- `api/types.ts`: carries the derived number only on the frontend `OverlayBox` view type.
- `ProjectWorkbenchApp.tsx`: associates backend candidate records with the derived view number.
- `InspectionWorkbench.tsx`: derives the shared lookup from numbered candidates and passes it to list/summary.
- `OverlayLayer.tsx`: renders one accessible blue candidate marker per item and suppresses it when an active formal balloon exists.
- `InspectionItemTable.tsx`: applies formal → candidate → unknown display precedence.
- `workbench.css`: differentiates candidate and formal number circles without changing the existing design system.
- `chinese-pdf-upload-mvp.spec.ts`: proves the runtime state transition through the naked-root product flow.

### Task 6: Show Candidate Numbers Before Formal Balloon Generation

**Files:**

- Create: `frontend/src/components/workbench/candidateNumbering.ts`
- Create: `frontend/src/components/workbench/candidateNumbering.test.ts`
- Modify: all remaining paths listed under `Allowed Paths`

- [ ] **Step 1: Write the pure-function RED test**

Create `candidateNumbering.test.ts`:

```ts
import { describe, expect, test } from "vitest";

import { deriveCandidateNumbers } from "./candidateNumbering";

describe("deriveCandidateNumbers", () => {
  test("numbers only active review items in stable working-copy order", () => {
    const result = deriveCandidateNumbers([
      { item_id: "item-b", raw_text: "20", active: true },
      { item_id: "excluded", raw_text: "30", active: false },
      { item_id: "item-a", raw_text: "10", active: true },
    ]);

    expect([...result.entries()]).toEqual([
      ["item-b", 1],
      ["item-a", 2],
    ]);
  });
});
```

- [ ] **Step 2: Run the pure-function test and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- \
  --run src/components/workbench/candidateNumbering.test.ts
```

Expected: FAIL because `candidateNumbering.ts` or `deriveCandidateNumbers` does not exist.

- [ ] **Step 3: Implement the minimal pure derivation**

Create `candidateNumbering.ts`:

```ts
import type { ReviewItem } from "../../api/types";

export type CandidateNumberMap = ReadonlyMap<string, number>;

export function deriveCandidateNumbers(
  items: readonly ReviewItem[],
): CandidateNumberMap {
  const result = new Map<string, number>();
  let number = 1;
  for (const item of items) {
    if (!item.active) continue;
    result.set(item.item_id, number);
    number += 1;
  }
  return result;
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command.

Expected: one test file and one test pass.

- [ ] **Step 5: Write the overlay RED tests**

Extend `OverlayLayer.test.tsx` with a candidate that contains `itemId` and `candidateNumber`.

Required assertions:

```ts
test("renders one selectable provisional number until a formal balloon exists", () => {
  const onSelect = vi.fn();
  const candidate = {
    id: "c1",
    itemId: "item-1",
    candidateNumber: 12,
    bbox: [10, 20, 30, 40] as [number, number, number, number],
  };
  const { rerender } = render(
    <OverlayLayer
      pageWidth={100}
      pageHeight={100}
      scale={1}
      candidates={[candidate]}
      sources={[]}
      balloons={[]}
      onSelectItem={onSelect}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "候选气泡 12" }));
  expect(onSelect).toHaveBeenCalledWith("item-1");

  rerender(
    <OverlayLayer
      pageWidth={100}
      pageHeight={100}
      scale={1}
      candidates={[candidate]}
      sources={[]}
      balloons={[{
        id: "b1",
        itemId: "item-1",
        center: [60, 60],
        number: 7,
        status: "active",
      }]}
      onSelectItem={onSelect}
    />,
  );

  expect(screen.queryByRole("button", { name: "候选气泡 12" })).toBeNull();
  expect(screen.getByTestId("balloon-b1").textContent).toContain("7");
});
```

Add a duplicate-candidate assertion: when two candidate boxes share the same `itemId`, exactly one accessible candidate marker is rendered.

- [ ] **Step 6: Run the overlay test and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- \
  --run src/components/pdf/OverlayLayer.test.tsx
```

Expected: FAIL because `OverlayBox.candidateNumber` and the accessible candidate marker do not exist.

- [ ] **Step 7: Carry candidate numbers into the view model**

Extend `OverlayBox` in `frontend/src/api/types.ts`:

```ts
export type OverlayBox = {
  id: string;
  itemId?: string;
  itemIds?: string[];
  pageIndex?: number;
  bbox: PdfCoordinates;
  rawText?: string;
  candidateNumber?: number;
};
```

In `ProjectWorkbenchApp.tsx`, derive the map from the current working copy:

```ts
const candidateNumbers = useMemo(
  () => deriveCandidateNumbers(snapshot?.working_copy.items ?? []),
  [snapshot?.working_copy.items],
);
```

Add `candidateNumber` to each mapped candidate:

```ts
candidateNumber: candidateNumbers.get(candidate.item_id),
```

Import `deriveCandidateNumbers` from `./candidateNumbering`.

- [ ] **Step 8: Implement the accessible SVG candidate marker**

In `OverlayLayer.tsx`:

1. build a `Set` of item IDs with active formal balloons;
2. choose only the first candidate for each `itemId` as the numbered marker;
3. keep rendering every candidate rectangle;
4. render numbered markers after source rectangles and before formal balloons.

Use this positioning rule:

```ts
const radius = 10;
const markerX = Math.min(
  pageWidth - radius - 1,
  Math.max(radius + 1, x1 + radius + 2),
);
const markerY = Math.min(
  pageHeight - radius - 1,
  Math.max(radius + 1, y0 - radius - 2),
);
```

The marker group must contain:

```tsx
<g
  role="button"
  tabIndex={selectItem === undefined ? undefined : 0}
  aria-label={zhCN.pdf.candidateBalloon(item.candidateNumber)}
  data-testid={`candidate-number-${item.id}`}
  data-selected={isSelected}
  onClick={() => selectItem?.(item.itemId as string)}
  onKeyDown={(event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectItem?.(item.itemId as string);
    }
  }}
  style={{ cursor: selectItem ? "pointer" : "default" }}
>
  <circle
    cx={markerX}
    cy={markerY}
    r={radius}
    fill={isSelected ? "#2563eb" : "#eff6ff"}
    stroke="#2563eb"
    strokeWidth={isSelected ? 2.5 : 1.5}
  />
  <text
    x={markerX}
    y={markerY}
    fill={isSelected ? "#ffffff" : "#1d4ed8"}
    fontSize="9"
    fontWeight="700"
    textAnchor="middle"
    dominantBaseline="central"
    pointerEvents="none"
  >
    {item.candidateNumber}
  </text>
</g>
```

Add to `zhCN.pdf`:

```ts
candidateBalloon: (number: number) => `候选气泡 ${number}`,
```

- [ ] **Step 9: Run the overlay and pure-function tests and verify GREEN**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- \
  --run \
  src/components/workbench/candidateNumbering.test.ts \
  src/components/pdf/OverlayLayer.test.tsx
```

Expected: both test files pass.

- [ ] **Step 10: Write list and summary RED tests**

Extend `InspectionItemTable.test.tsx`:

```ts
test("shows candidate numbers before formal numbers and lets formal numbers win", () => {
  const items = [
    { item_id: "i1", raw_text: "10", active: true },
    { item_id: "i2", raw_text: "20", active: true },
  ];
  const candidateNumbers = new Map([["i1", 1], ["i2", 2]]);
  const { rerender } = render(
    <InspectionItemTable
      items={items}
      balloons={[]}
      candidateNumbers={candidateNumbers}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  expect(screen.getByRole("row", { name: /10/ }).textContent).toContain("1");
  expect(screen.getByRole("row", { name: /20/ }).textContent).toContain("2");

  rerender(
    <InspectionItemTable
      items={items}
      balloons={[{
        id: "b1",
        itemId: "i1",
        center: [1, 1],
        number: 9,
        status: "active",
      }]}
      candidateNumbers={candidateNumbers}
      filter="all"
      onSelectItem={vi.fn()}
    />,
  );

  const formal = screen.getByRole("row", { name: /10/ })
    .querySelector(".inspection-number");
  expect(formal?.textContent).toBe("9");
  expect(formal?.getAttribute("data-kind")).toBe("formal");
});
```

Extend `ProjectWorkbenchApp.test.tsx` with a response containing active items, candidates and no balloons. Assert the rendered PDF overlay exposes `候选气泡 1` and the selected summary displays `1`.

- [ ] **Step 11: Run the list/workbench tests and verify RED**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- \
  --run \
  src/components/workbench/InspectionItemTable.test.tsx \
  src/components/workbench/ProjectWorkbenchApp.test.tsx
```

Expected: FAIL because table and summary do not accept or render candidate numbers.

- [ ] **Step 12: Wire the shared map into table and summary**

In `InspectionWorkbench.tsx`, derive the read-only lookup from numbered candidates:

```ts
const candidateNumbers = useMemo(
  () => new Map(
    candidates.flatMap((candidate) => (
      candidate.itemId === undefined || candidate.candidateNumber === undefined
        ? []
        : [[candidate.itemId, candidate.candidateNumber] as const]
    )),
  ),
  [candidates],
);
```

Pass `candidateNumber={candidateNumbers.get(selectedReviewItem.item_id)}` to `SelectedInspectionItemSummary` and `candidateNumbers={candidateNumbers}` to `InspectionItemTable`.

Update both components so number display uses:

```ts
const displayedNumber = balloon?.number ?? candidateNumber;
```

For each table row:

```tsx
<strong
  role="cell"
  className="inspection-number"
  data-kind={balloon === undefined
    ? candidateNumber === undefined ? "empty" : "candidate"
    : "formal"}
  aria-label={balloon === undefined && candidateNumber !== undefined
    ? zhCN.inspection.candidateNumber(candidateNumber)
    : undefined}
>
  {balloon?.number ?? candidateNumber ?? zhCN.workbench.unknown}
</strong>
```

Add:

```ts
candidateNumber: (number: number) => `候选序号 ${number}`,
```

to `zhCN.inspection`.

In `workbench.css`, preserve the existing formal red style and add:

```css
.inspection-number[data-kind="candidate"] {
  border-color: var(--qi-blue);
  background: #eff6ff;
  color: #1d4ed8;
}

.inspection-number[data-kind="empty"] {
  border-color: var(--qi-border);
  color: var(--qi-muted);
}
```

- [ ] **Step 13: Run the focused tests and verify GREEN**

Run the Step 11 command.

Expected: both test files pass.

- [ ] **Step 14: Add the browser regression assertion**

In `frontend/e2e/chinese-pdf-upload-mvp.spec.ts`, immediately after the workbench becomes visible and before any review command:

```ts
const candidateBalloons = page.getByRole("button", {
  name: /^候选气泡 [1-9]\d*$/,
});
await expect(candidateBalloons.first()).toBeVisible();
expect(await candidateBalloons.count()).toBeGreaterThan(0);
```

Immediately after the existing successful Generate Balloons action:

```ts
await expect(candidateBalloons).toHaveCount(0);
await expect(page.locator("[data-testid^='balloon-']").first()).toBeVisible();
```

Keep every existing UI-only, download, no-ID-leak and console/network assertion.

- [ ] **Step 15: Run complete static and component verification**

Run:

```bash
micromamba run -n qi-p0 npm --prefix frontend test -- --run
micromamba run -n qi-p0 npm --prefix frontend run build
micromamba run -n qi-p0 npm --prefix frontend run e2e -- --list
python .agent/harness/scripts/check-contracts.py
git diff --check
```

Expected:

- all frontend Vitest files pass;
- production build succeeds with no new warning;
- both Playwright tests remain discoverable;
- contract checker reports zero drift;
- diff check succeeds.

- [ ] **Step 16: Run the real 4173 browser closure**

Run:

```bash
QI_MVP_BASE_URL=http://127.0.0.1:4173 \
QI_MVP_E2E_PDF=/tmp/qi-task5-real.pdf \
micromamba run -n qi-p0 npm --prefix frontend run e2e -- \
  e2e/chinese-pdf-upload-mvp.spec.ts
```

Expected:

- naked `/` upload succeeds;
- before freeze, one or more blue positive-integer candidate balloons are visible;
- after formal generation, candidate balloon count becomes zero;
- red formal balloon numbers are visible;
- PDF, Excel and manifest closure remains green;
- no unexplained Console or Network error.

Capture one 1565×796 Chrome screenshot before freeze and one after formal generation under `/tmp`; do not stage them.

- [ ] **Step 17: Request independent reviews**

Spec reviewer checks:

- blue numbers are frontend-only provisional display;
- no API mutation or formal-number shortcut was added;
- excluded items and duplicate candidates do not receive misleading duplicate markers;
- active formal balloons suppress provisional markers;
- formal freeze→generate→confirm→export order remains intact.

Code-quality reviewer checks:

- one pure mapping Owner;
- no quadratic or stateful numbering drift;
- keyboard and Chinese accessible names work;
- tests reproduce the real “124 candidates, 0 balloons” failure;
- no unrelated file or dependency changes.

Any blocking issue is fixed with the same TDD checks and re-reviewed.

- [ ] **Step 18: Commit Task 6**

Review exact scope:

```bash
git status --short
git diff --check
git diff --name-only
```

Stage only Task 6 implementation paths:

```bash
git add \
  frontend/src/api/types.ts \
  frontend/src/copy/zhCN.ts \
  frontend/src/components/workbench/candidateNumbering.ts \
  frontend/src/components/workbench/candidateNumbering.test.ts \
  frontend/src/components/workbench/ProjectWorkbenchApp.tsx \
  frontend/src/components/workbench/ProjectWorkbenchApp.test.tsx \
  frontend/src/components/workbench/InspectionWorkbench.tsx \
  frontend/src/components/workbench/InspectionItemTable.tsx \
  frontend/src/components/workbench/InspectionItemTable.test.tsx \
  frontend/src/components/pdf/OverlayLayer.tsx \
  frontend/src/components/pdf/OverlayLayer.test.tsx \
  frontend/src/styles/workbench.css \
  frontend/e2e/chinese-pdf-upload-mvp.spec.ts
git diff --cached --check
git commit -m "feat: show candidate balloon numbers"
```

Do not stage `.gitignore`, `AGENTS.md`, `.local/`, `__pycache__/`, screenshots or Playwright output.

## Final Stop Boundary

Stop after Task 6 verification, independent review and commit. Do not change automatic freeze semantics, backend numbering, balloon placement algorithms, export formats, authentication, project dashboards or deployment configuration.
