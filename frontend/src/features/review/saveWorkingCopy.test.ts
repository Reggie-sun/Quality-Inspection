import { describe, expect, test, vi } from "vitest";

import { saveWorkingCopy } from "./saveWorkingCopy";


describe("saveWorkingCopy", () => {
  test("P0-UI-007 save sends version and operator without freezing", async () => {
    const post = vi.fn().mockResolvedValue({ version: 4 });

    await saveWorkingCopy(post, "p1", "quality-1", 3, {
      type: "keep",
      item_id: "i1",
    });

    expect(post).toHaveBeenCalledWith(
      "/api/v1/projects/p1/review/commands",
      { expected_version: 3, command: { type: "keep", item_id: "i1" } },
      { "X-QI-Operator": "quality-1" },
    );
    expect(post.mock.calls[0][0]).not.toContain("freeze");
  });
});
