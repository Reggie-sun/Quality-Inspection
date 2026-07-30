import { beforeEach, describe, expect, it } from "vitest";

import {
  LOCAL_DRAWING_REGISTRY_KEY,
  readLocalDrawings,
  registerLocalDrawing,
  touchLocalDrawing,
  type LocalDrawingEntry,
} from "./localDrawingRegistry";


const PROJECT_A = "11111111-1111-4111-8111-111111111111";
const PROJECT_B = "22222222-2222-4222-8222-222222222222";
const FIRST = new Date("2026-07-30T01:00:00.000Z");
const SECOND = new Date("2026-07-30T02:00:00.000Z");
const THIRD = new Date("2026-07-30T03:00:00.000Z");


describe("localDrawingRegistry", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("keeps multiple drawings and sorts by last opened time", () => {
    registerLocalDrawing(PROJECT_A, "A.pdf", FIRST);
    registerLocalDrawing(PROJECT_B, "B.pdf", SECOND);

    expect(readLocalDrawings().map((entry) => entry.projectId)).toEqual([
      PROJECT_B,
      PROJECT_A,
    ]);
  });

  it("updates an existing drawing without replacing other entries", () => {
    registerLocalDrawing(PROJECT_A, "A.pdf", FIRST);
    registerLocalDrawing(PROJECT_B, "B.pdf", SECOND);

    expect(touchLocalDrawing(PROJECT_A, undefined, THIRD)).toBe(true);
    expect(readLocalDrawings()).toMatchObject([
      {
        projectId: PROJECT_A,
        fileName: "A.pdf",
        createdAt: FIRST.toISOString(),
        lastOpenedAt: THIRD.toISOString(),
      },
      {
        projectId: PROJECT_B,
        fileName: "B.pdf",
        createdAt: SECOND.toISOString(),
        lastOpenedAt: SECOND.toISOString(),
      },
    ]);
  });

  it("deduplicates stored entries by project id", () => {
    const entries: LocalDrawingEntry[] = [
      {
        projectId: PROJECT_A,
        fileName: "older.pdf",
        createdAt: FIRST.toISOString(),
        lastOpenedAt: FIRST.toISOString(),
      },
      {
        projectId: PROJECT_A,
        fileName: "newer.pdf",
        createdAt: FIRST.toISOString(),
        lastOpenedAt: THIRD.toISOString(),
      },
    ];
    window.localStorage.setItem(
      LOCAL_DRAWING_REGISTRY_KEY,
      JSON.stringify(entries),
    );

    expect(readLocalDrawings()).toEqual([entries[1]]);
  });

  it("filters malformed entries and tolerates malformed JSON", () => {
    const validEntry: LocalDrawingEntry = {
      projectId: PROJECT_A,
      fileName: "A.pdf",
      createdAt: FIRST.toISOString(),
      lastOpenedAt: SECOND.toISOString(),
    };
    window.localStorage.setItem(
      LOCAL_DRAWING_REGISTRY_KEY,
      JSON.stringify([
        validEntry,
        { ...validEntry, projectId: "not-a-uuid" },
        { ...validEntry, fileName: " " },
        { ...validEntry, createdAt: "not-a-date" },
      ]),
    );

    expect(readLocalDrawings()).toEqual([validEntry]);

    window.localStorage.setItem(LOCAL_DRAWING_REGISTRY_KEY, "{");
    expect(readLocalDrawings()).toEqual([]);
  });

  it("uses a fallback name when touching an unknown drawing", () => {
    expect(
      touchLocalDrawing(PROJECT_A, "未命名图纸.pdf", FIRST),
    ).toBe(true);

    expect(readLocalDrawings()).toEqual([
      {
        projectId: PROJECT_A,
        fileName: "未命名图纸.pdf",
        createdAt: FIRST.toISOString(),
        lastOpenedAt: FIRST.toISOString(),
      },
    ]);
  });

  it("rejects invalid writes without changing storage", () => {
    expect(registerLocalDrawing("invalid", "A.pdf", FIRST)).toBe(false);
    expect(registerLocalDrawing(PROJECT_A, " ", FIRST)).toBe(false);
    expect(registerLocalDrawing(PROJECT_A, "A.pdf", new Date("invalid")))
      .toBe(false);
    expect(readLocalDrawings()).toEqual([]);
  });

  it("returns safe results when storage access fails", () => {
    const blocked = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
    } as unknown as Storage;

    expect(readLocalDrawings(blocked)).toEqual([]);
    expect(registerLocalDrawing(PROJECT_A, "A.pdf", FIRST, blocked)).toBe(false);
  });
});
