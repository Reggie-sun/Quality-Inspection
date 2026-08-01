import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, expect, test, vi } from "vitest";

import type { ProjectWorkbenchView } from "../../api/types";
import { ProjectWorkbenchApp } from "./ProjectWorkbenchApp";


afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});


function reviewedResponse(): ProjectWorkbenchView {
  return {
    project: { id: "project-real", state: "reviewed", version: 1 },
    working_copy: {
      id: "working-real",
      project_id: "project-real",
      raw_result_id: "raw-real",
      version: 7,
      items: [{
        item_id: "item-secret-uuid",
        item_type: "thread",
        raw_text: "M6",
        coordinates: [10, 20, 30, 40],
        balloon_required: true,
        requires_confirmation: false,
        page_index: 0,
        status: "kept",
        active: true,
      }],
      coverage: { blocking_count: 0, review_required_count: 0 },
      numbering_stale: false,
      items_frozen_at: "2026-07-23T01:00:00Z",
      items_frozen_by: "operator-secret-uuid",
      items_frozen_version: 7,
      sip_metadata: {
        material_code: "MAT-001",
        material_name: "上座",
        drawing_number: "JS26032501",
        material: "SUS304",
        revision: "A1",
      },
    },
    pages: [{
      page_index: 0,
      width: 200,
      height: 200,
      pdf_to_render_matrix: [1, 0, 0, 1, 0, 0],
      render_to_pdf_matrix: [1, 0, 0, 1, 0, 0],
    }],
    candidates: [],
    sources: [],
    sip_metadata_suggestions: [],
    balloons: [{
      id: "balloon-secret-uuid",
      project_id: "project-real",
      inspection_item_id: "item-secret-uuid",
      source_location_id: "source-secret-uuid",
      page_index: 0,
      suggested_number: 1,
      formal_number: 1,
      sort_order: 0,
      anchor_bbox_pdf: [10, 20, 30, 40],
      leader_target_pdf: [20, 30],
      center_pdf: [50, 60],
      placement_status: "placed",
      collision_flags: [],
      status: "active",
      version: 1,
    }],
    balloon_blockers: [],
    source_pdf_url: "/api/v1/projects/project-real/source-pdf",
    reviewed_result_id: "reviewed-secret-uuid",
    latest_export: {
      id: "export-secret-uuid",
      project_id: "project-real",
      reviewed_result_id: "reviewed-secret-uuid",
      status: "success",
      error_id: null,
      template_version: "template/1",
      mapping_version: "mapping/1",
      renderer_version: "renderer/1",
      artifacts: [
        {
          kind: "ballooned_pdf",
          sha256: "pdf-sha256",
          size_bytes: 1,
          reviewed_result_id: "reviewed-secret-uuid",
          downloadable: true,
        },
        {
          kind: "sip_excel",
          sha256: "excel-sha256",
          size_bytes: 1,
          reviewed_result_id: "reviewed-secret-uuid",
          downloadable: true,
        },
        {
          kind: "manifest",
          sha256: "manifest-sha256",
          size_bytes: 1,
          reviewed_result_id: "reviewed-secret-uuid",
          downloadable: true,
        },
      ],
    },
  } as ProjectWorkbenchView;
}

test("workbench title-block suggestions adopt recognized values without submitting incomplete metadata", async () => {
  const snapshot = reviewedResponse();
  snapshot.project.state = "editing";
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.working_copy.sip_metadata = {};
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;
  snapshot.sip_metadata_suggestions = [{
    field: "drawing_number",
    value: "ZHZS25032501-04",
    observation_id: "drawing-number-value",
    label_observation_id: "drawing-number-label",
    page_index: 0,
    bbox_pdf: [1088.29, 781.55, 1162.57, 796.3],
    rule_version: "welli-title-metadata/1",
    evidence_codes: ["native_line"],
  }];
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  fireEvent.click(await screen.findByRole("button", {
    name: "展开检验、导出与处理信息",
  }));
  const sipRegion = await screen.findByRole("region", { name: "SIP 信息" });
  fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  expect((
    within(sipRegion).getByRole("textbox", {
      name: "图号",
    }) as HTMLInputElement
  ).value).toBe("ZHZS25032501-04");
  expect(within(sipRegion).getByText("图纸识别，已自动采纳")).not.toBeNull();
  expect(within(sipRegion).getByText(
    "系统已自动采纳 1/4，待补充：物料编码、产品名称、版本号",
  )).not.toBeNull();
  expect(fetchMock.mock.calls.some(([path]) => (
    String(path).endsWith("/review/commands")
  ))).toBe(false);
});


test("工作台加载态使用中文并标记 aria-busy", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn()}
    />,
  );

  const loading = screen.getByText("正在加载审核工作台");
  expect(loading.closest("[aria-busy='true']")).not.toBeNull();
});


test.each([
  ["review_lock_conflict", "审核项目正由其他人员编辑，请稍后重试。"],
  ["unknown_backend_code", "操作失败，请重试。"],
])("ApiError %s 只显示安全中文，不显示后端 message", async (code, expected) => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    error: { code, message: "RAW backend secret path /srv/private" },
  }), {
    status: 409,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn()}
    />,
  );

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(expected);
  expect(alert.textContent).not.toContain("RAW backend secret");
  expect(alert.textContent).not.toContain("/srv/private");
});


test("审核锁冲突时仍可回到图纸列表", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    error: {
      code: "review_lock_conflict",
      message: "project is locked by another operator",
    },
  }), {
    status: 409,
    headers: { "Content-Type": "application/json" },
  })));
  const onReset = vi.fn();

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn()}
      onReset={onReset}
    />,
  );

  expect((await screen.findByRole("alert")).textContent).toContain(
    "审核项目正由其他人员编辑，请稍后重试。",
  );
  fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
  expect(onReset).toHaveBeenCalledOnce();
});


test("返回图纸列表时用最后一次 lease version 主动释放审核锁", async () => {
  const snapshot = reviewedResponse();
  const expiresAt = "2026-08-01T09:05:00Z";
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => {
    if (String(path).endsWith("/review/lock/release")) {
      return new Response(JSON.stringify({
        project_id: "project-real",
        released: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify(
      String(path).endsWith("/review/lock")
        ? {
            project_id: "project-real",
            operator_id: "operator-real",
            expires_at: expiresAt,
          }
        : snapshot,
    ), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  const onReset = vi.fn();

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
      onReset={onReset}
    />,
  );

  fireEvent.click(await screen.findByRole("button", { name: "回到图纸列表" }));
  expect(onReset).toHaveBeenCalledOnce();
  await waitFor(() => expect(fetchMock.mock.calls.some(([path, init]) => (
    String(path).endsWith("/review/lock/release")
      && init?.method === "POST"
      && init.keepalive === true
      && init.headers !== undefined
      && (init.headers as Record<string, string>)["X-QI-Operator"] === "operator-real"
      && JSON.parse(String(init.body)).expires_at === expiresAt
  ))).toBe(true));
});


test("pagehide 主动释放 lease，React cleanup 本身不发送 release", async () => {
  const snapshot = reviewedResponse();
  const expiresAt = "2026-08-01T09:05:00Z";
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? {
          project_id: "project-real",
          operator_id: "operator-real",
          expires_at: expiresAt,
        }
      : String(path).endsWith("/review/lock/release")
        ? { project_id: "project-real", released: true }
        : snapshot,
  ), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);

  const rendered = render(
    <StrictMode>
      <ProjectWorkbenchApp
        projectId="project-real"
        operatorId="operator-real"
        loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
      />
    </StrictMode>,
  );

  await screen.findByRole("region", { name: "项目摘要" });
  rendered.unmount();
  expect(fetchMock.mock.calls.some(([path]) => (
    String(path).endsWith("/review/lock/release")
  ))).toBe(false);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );
  await screen.findByRole("region", { name: "项目摘要" });
  fireEvent(window, new Event("pagehide"));

  await waitFor(() => expect(fetchMock.mock.calls.some(([path, init]) => (
    String(path).endsWith("/review/lock/release")
      && init?.keepalive === true
  ))).toBe(true));
});


test("hidden 页面跳过 interval renew，恢复 visible 时立即续期", async () => {
  vi.useFakeTimers();
  let visibility: DocumentVisibilityState = "visible";
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  const snapshot = reviewedResponse();
  let leaseNumber = 0;
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => {
    if (String(path).endsWith("/review/lock")) {
      leaseNumber += 1;
      return new Response(JSON.stringify({
        project_id: "project-real",
        operator_id: "operator-real",
        expires_at: `2026-08-01T09:0${leaseNumber}:00Z`,
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify(snapshot), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );
  await vi.advanceTimersByTimeAsync(0);
  expect(leaseNumber).toBe(1);

  visibility = "hidden";
  await vi.advanceTimersByTimeAsync(240_000);
  expect(leaseNumber).toBe(1);

  visibility = "visible";
  fireEvent(document, new Event("visibilitychange"));
  await vi.advanceTimersByTimeAsync(0);
  expect(leaseNumber).toBe(2);
});


test.each([
  { scenario: "reset", leaveBy: "reset", resumeFromBfcache: false },
  { scenario: "pagehide", leaveBy: "pagehide", resumeFromBfcache: false },
  { scenario: "bfcache", leaveBy: "pagehide", resumeFromBfcache: true },
] as const)(
  "$scenario 离开时等待中的 renew 保持 single-flight 并协调最新 lease release",
  async ({ leaveBy, resumeFromBfcache }) => {
    const snapshot = reviewedResponse();
    const firstExpiry = "2026-08-01T09:05:00Z";
    const renewedExpiry = "2026-08-01T09:09:00Z";
    let lockCalls = 0;
    let resolveRenewal!: () => void;
    const renewalGate = new Promise<void>((resolve) => {
      resolveRenewal = resolve;
    });
    const releasedVersions: string[] = [];
    const fetchMock = vi.fn(async (
      path: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      if (String(path).endsWith("/review/lock/release")) {
        releasedVersions.push(JSON.parse(String(init?.body)).expires_at);
        return new Response(JSON.stringify({
          project_id: "project-real",
          released: true,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (String(path).endsWith("/review/lock")) {
        lockCalls += 1;
        if (lockCalls > 1) await renewalGate;
        return new Response(JSON.stringify({
          project_id: "project-real",
          operator_id: "operator-real",
          expires_at: lockCalls === 1 ? firstExpiry : renewedExpiry,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onReset = vi.fn();

    render(
      <ProjectWorkbenchApp
        projectId="project-real"
        operatorId="operator-real"
        loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
        onReset={onReset}
      />,
    );
    await screen.findByRole("region", { name: "项目摘要" });

    fireEvent.focus(window);
    fireEvent(window, new Event("pageshow"));
    if (leaveBy === "reset") {
      fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
    } else {
      fireEvent(window, new Event("pagehide"));
    }
    await waitFor(() => expect(releasedVersions).toEqual([firstExpiry]));
    if (resumeFromBfcache) {
      fireEvent(window, new Event("pageshow"));
    }

    await act(async () => {
      resolveRenewal();
      await renewalGate;
    });
    if (resumeFromBfcache) {
      expect(lockCalls).toBe(2);
      expect(releasedVersions).toEqual([firstExpiry]);
      fireEvent(window, new Event("pagehide"));
    }
    await waitFor(() => expect(releasedVersions).toEqual([
      firstExpiry,
      renewedExpiry,
    ]));
    expect(lockCalls).toBe(2);
    expect(onReset).toHaveBeenCalledTimes(leaveBy === "reset" ? 1 : 0);
  },
);


test("刷新后从只读 projection 恢复 reviewed result 和三项下载", async () => {
  const snapshot = reviewedResponse();
  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => {
    if (String(path).endsWith("/review/lock")) {
      return new Response(JSON.stringify({ operator_id: "operator-real" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(snapshot), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  fireEvent.click(await screen.findByRole("button", {
    name: "展开检验、导出与处理信息",
  }));
  await waitFor(() => expect(screen.getAllByRole("link")).toHaveLength(3));
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "下载带气泡 PDF",
    "下载 SIP Excel",
    "下载校验清单",
  ]);
  expect(fetchMock.mock.calls.some(([path, init]) => (
    String(path).endsWith("/exports") && init?.method === "POST"
  ))).toBe(false);
  expect(document.body.textContent).not.toContain("project-real");
  expect(document.body.textContent).not.toContain("operator-real");
  expect(document.body.textContent).not.toContain("item-secret-uuid");
});

test("就绪页头部横向组合纯文字品牌、真实阶段和重新处理入口", async () => {
  const snapshot = reviewedResponse();
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));
  const onReset = vi.fn();

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
      onReset={onReset}
    />,
  );

  const compactHeader = await screen.findByRole("group", {
    name: "项目与审核操作",
  });
  expect(screen.queryByRole("navigation", {
    name: "检验处理阶段",
  })).toBeNull();
  expect(screen.queryByRole("banner", {
    name: "工程图纸检验流程",
  })).toBeNull();

  fireEvent.click(within(compactHeader).getByRole("button", {
    name: "回到图纸列表",
  }));
  expect(onReset).toHaveBeenCalledOnce();
});


test("工作台加载完成后不保留过期识别状态", async () => {
  const snapshot = reviewedResponse();
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  expect(await screen.findByRole("region", { name: "项目摘要" })).not.toBeNull();
  expect(screen.queryByText("识别完成，已进入审核")).toBeNull();
});


test("无正式气泡时显示非正式候选编号并在检验项详情复用候选序号", async () => {
  const snapshot = reviewedResponse();
  snapshot.project.state = "editing";
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.candidates = [{
    id: "candidate-secret-uuid",
    item_id: "item-secret-uuid",
    page_index: 0,
    bbox_pdf: [10, 20, 30, 40],
  }];
  snapshot.balloons = [];
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
    _init?: RequestInit,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  expect(await screen.findByRole("button", {
    name: "候选编号 1（非正式气泡）",
  })).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "筛选全部" }));
  fireEvent.click(screen.getByRole("row", { name: /M6/ }));
  const detail = screen.getByRole("article", { name: "检验项 1 · 螺纹" });
  expect(within(detail).getByText("候选序号 1")).not.toBeNull();
});

test("后端 auto_accepted status/disposition 原样投影为红色 provisional marker", async () => {
  const snapshot = reviewedResponse();
  snapshot.project.state = "editing";
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.working_copy.manual_review_count = 0;
  snapshot.working_copy.items[0] = {
    ...snapshot.working_copy.items[0],
    status: "auto_accepted",
    acceptance_source: "confidence_policy",
    confidence_decision: {
      band: "high",
      review_disposition: "auto_accepted",
      policy_version: "candidate-confidence/1",
      evidence_codes: ["typed_schema_complete"],
    },
  };
  snapshot.candidates = [{
    id: "candidate-secret-uuid",
    item_id: "item-secret-uuid",
    page_index: 0,
    bbox_pdf: [10, 20, 30, 40],
    confidence_band: "high",
    review_disposition: "auto_accepted",
    status: "auto_accepted",
  }];
  snapshot.balloons = [];
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  const marker = await screen.findByRole("button", {
    name: "自动通过气泡 1",
  });
  expect(marker.querySelector("circle")?.getAttribute("stroke")).toBe("#c23b3b");
});

test("candidate 单边自动投影不得绕过 working item 完整合同", async () => {
  const snapshot = reviewedResponse();
  const validDecision = {
    band: "high" as const,
    review_disposition: "auto_accepted" as const,
    policy_version: "candidate-confidence/1" as const,
    evidence_codes: ["typed_schema_complete"],
  };
  snapshot.project.state = "editing";
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.working_copy.manual_review_count = 3;
  snapshot.working_copy.items = [
    {
      ...snapshot.working_copy.items[0],
      item_id: "requires-confirmation",
      raw_text: "10",
      status: "auto_accepted",
      requires_confirmation: true,
      acceptance_source: "confidence_policy",
      confidence_decision: validDecision,
    },
    {
      ...snapshot.working_copy.items[0],
      item_id: "missing-acceptance-source",
      raw_text: "20",
      status: "auto_accepted",
      requires_confirmation: false,
      acceptance_source: undefined,
      confidence_decision: validDecision,
    },
    {
      ...snapshot.working_copy.items[0],
      item_id: "mismatched-policy",
      raw_text: "30",
      status: "auto_accepted",
      requires_confirmation: false,
      acceptance_source: "confidence_policy",
      confidence_decision: {
        ...validDecision,
        policy_version: "future-policy",
      } as never,
    },
  ];
  snapshot.candidates = snapshot.working_copy.items.map((item, index) => ({
    id: `candidate-${item.item_id}`,
    item_id: item.item_id,
    page_index: 0,
    bbox_pdf: [10 + index * 40, 20, 30 + index * 40, 40],
    confidence_band: "high",
    review_disposition: "auto_accepted",
    status: "auto_accepted",
  }));
  snapshot.balloons = [];
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;
  vi.stubGlobal("fetch", vi.fn(async (
    path: RequestInfo | URL,
  ) => new Response(JSON.stringify(
    String(path).endsWith("/review/lock")
      ? { operator_id: "operator-real" }
      : snapshot,
  ), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })));

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
    />,
  );

  for (const [number, rawText] of [[1, "10"], [2, "20"], [3, "30"]] as const) {
    expect(await screen.findByRole("button", {
      name: `候选编号 ${number}（非正式气泡）`,
    })).not.toBeNull();
    expect(screen.queryByRole("button", {
      name: `自动通过气泡 ${number}`,
    })).toBeNull();
    expect(screen.getByRole("row", { name: new RegExp(rawText) })).not.toBeNull();
  }
});

test("保存并返回的连续命令使用每次刷新后的最新 working copy version", async () => {
  let currentVersion = 7;
  const expectedVersions: number[] = [];
  const snapshot = reviewedResponse();
  snapshot.project.state = "editing";
  snapshot.working_copy.items = [];
  snapshot.working_copy.version = currentVersion;
  snapshot.working_copy.coverage = {
    blocking_count: 1,
    review_required_count: 0,
  };
  snapshot.working_copy.items_frozen_at = null;
  snapshot.working_copy.items_frozen_by = null;
  snapshot.working_copy.items_frozen_version = null;
  snapshot.balloons = [];
  snapshot.reviewed_result_id = null;
  snapshot.latest_export = null;

  const fetchMock = vi.fn(async (
    path: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    if (String(path).endsWith("/review/lock")) {
      return new Response(JSON.stringify({ operator_id: "operator-real" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (String(path).endsWith("/review/commands")) {
      const body = JSON.parse(String(init?.body)) as {
        expected_version: number;
      };
      expectedVersions.push(body.expected_version);
      currentVersion += 1;
      return new Response(JSON.stringify({ version: currentVersion }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({
      ...snapshot,
      working_copy: {
        ...snapshot.working_copy,
        version: currentVersion,
      },
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  const onReset = vi.fn();

  render(
    <ProjectWorkbenchApp
      projectId="project-real"
      operatorId="operator-real"
      loadPdf={vi.fn().mockResolvedValue({ numPages: 1, getPage: vi.fn() })}
      onReset={onReset}
    />,
  );

  fireEvent.click(await screen.findByRole("button", {
    name: "展开检验、导出与处理信息",
  }));
  const sipRegion = await screen.findByRole("region", { name: "SIP 信息" });
  fireEvent.click(within(sipRegion).getByText("编辑项目 SIP 信息", {
    selector: "summary",
  }));
  fireEvent.change(within(sipRegion).getByRole("textbox", {
    name: "产品名称",
  }), { target: { value: "连续保存名称" } });
  fireEvent.change(screen.getByLabelText("新增检验项原始标注"), {
    target: { value: "M10" },
  });
  fireEvent.change(screen.getByLabelText("新增检验项坐标"), {
    target: { value: "1,2,3,4" },
  });

  fireEvent.click(screen.getByRole("button", { name: "回到图纸列表" }));
  fireEvent.click(screen.getByRole("button", { name: "保存并返回" }));

  await waitFor(() => expect(onReset).toHaveBeenCalledOnce());
  expect(expectedVersions).toEqual([7, 8]);
});
