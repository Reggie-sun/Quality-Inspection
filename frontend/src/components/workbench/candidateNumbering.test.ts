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

  test("自动通过项只获得稳定候选序号，不从 confidence 推断正式编号", () => {
    const items = [
      {
        item_id: "auto-item",
        raw_text: "10",
        status: "auto_accepted",
        requires_confirmation: false,
        acceptance_source: "confidence_policy" as const,
        confidence_decision: {
          band: "high" as const,
          review_disposition: "auto_accepted" as const,
          policy_version: "candidate-confidence/1" as const,
          evidence_codes: ["typed_schema_complete"],
        },
        balloon_required: true,
        active: true,
      },
      {
        item_id: "review-item",
        raw_text: "20",
        status: "pending",
        balloon_required: true,
        active: true,
      },
    ] satisfies ReviewItem[];

    expect(Array.from(deriveCandidateNumbers(items).entries())).toEqual([
      ["auto-item", 1],
      ["review-item", 2],
    ]);
    expect(candidateMarkerNumber(items[0], 1)).toBe(1);
  });
});
