import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { PostJson } from "../../api/types";
import { ExportPanel } from "./ExportPanel";


afterEach(cleanup);

test("P0-UI-004 gates export and exposes exactly three atomic backend downloads", async () => {
  const post = vi.fn().mockResolvedValue({
    id: "export-1",
    project_id: "project-1",
    reviewed_result_id: "reviewed-1",
    status: "success",
    artifacts: [
      { kind: "ballooned_pdf", downloadable: true },
      { kind: "sip_excel", downloadable: true },
      { kind: "manifest", downloadable: true },
    ],
  }) as unknown as PostJson;
  const { rerender } = render(
    <ExportPanel
      projectId="project-1"
      reviewedResultId={undefined}
      balloonBlockers={[]}
      post={post}
    />,
  );

  expect(screen.getByRole("button", { name: "Create formal export" })
    .hasAttribute("disabled")).toBe(true);
  expect(screen.queryAllByRole("link")).toHaveLength(0);

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={["manual_required"]}
      post={post}
    />,
  );
  expect(screen.getByRole("button", { name: "Create formal export" })
    .hasAttribute("disabled")).toBe(true);

  rerender(
    <ExportPanel
      projectId="project-1"
      reviewedResultId="reviewed-1"
      balloonBlockers={[]}
      post={post}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Create formal export" }));

  await waitFor(() => expect(post).toHaveBeenCalledWith(
    "/api/v1/projects/project-1/exports",
    { reviewed_result_id: "reviewed-1" },
    {},
  ));
  const downloads = screen.getAllByRole("link");
  expect(downloads.map((link) => link.textContent)).toEqual([
    "Download ballooned PDF",
    "Download SIP Excel",
    "Download manifest",
  ]);
  expect(downloads.map((link) => link.getAttribute("href"))).toEqual([
    "/api/v1/exports/export-1/downloads/ballooned_pdf",
    "/api/v1/exports/export-1/downloads/sip_excel",
    "/api/v1/exports/export-1/downloads/manifest",
  ]);
});
