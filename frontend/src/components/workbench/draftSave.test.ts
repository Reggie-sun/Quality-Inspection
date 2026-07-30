import { expect, it, vi } from "vitest";

import {
  saveDraftHandlesInOrder,
  type DraftSaveHandle,
} from "./draftSave";


it("saves each available draft handle in order", async () => {
  const calls: string[] = [];
  const handle = (name: string): DraftSaveHandle => ({
    saveDrafts: vi.fn(async () => {
      calls.push(name);
      return true;
    }),
  });

  expect(
    await saveDraftHandlesInOrder([
      handle("review"),
      null,
      handle("source"),
      handle("sip"),
    ]),
  ).toBe(true);
  expect(calls).toEqual(["review", "source", "sip"]);
});


it("stops at the first failed draft handle", async () => {
  const calls: string[] = [];
  const handle = (
    name: string,
    succeeds: boolean,
  ): DraftSaveHandle => ({
    saveDrafts: vi.fn(async () => {
      calls.push(name);
      return succeeds;
    }),
  });

  expect(
    await saveDraftHandlesInOrder([
      handle("review", true),
      handle("source", false),
      handle("sip", true),
    ]),
  ).toBe(false);
  expect(calls).toEqual(["review", "source"]);
});
