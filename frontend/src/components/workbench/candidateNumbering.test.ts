import { describe, expect, test } from "vitest";

import type { ReviewItem } from "../../api/types";
import {
  candidateMarkerNumber,
  deriveCandidateNumbers,
} from "./candidateNumbering";


describe("deriveCandidateNumbers", () => {
  test("仅按工作副本稳定顺序为有效项连续编号", () => {
    const items = [
      { item_id: "item-third", raw_text: "30", active: true },
      { item_id: "item-excluded", raw_text: "忽略", active: false },
      { item_id: "item-first", raw_text: "10", active: true },
    ] satisfies ReviewItem[];

    expect(Array.from(deriveCandidateNumbers(items).entries())).toEqual([
      ["item-third", 1],
      ["item-first", 2],
    ]);
  });

  test("无需气泡项保留候选序号但不向画布提供候选标记序号", () => {
    expect(candidateMarkerNumber({ balloon_required: false }, 66)).toBeUndefined();
    expect(candidateMarkerNumber({ balloon_required: true }, 66)).toBe(66);
    expect(candidateMarkerNumber({}, 66)).toBe(66);
  });
});
