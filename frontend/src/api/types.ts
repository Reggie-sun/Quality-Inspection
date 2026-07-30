export type PdfCoordinates = [number, number, number, number];
export type PdfMatrix = [number, number, number, number, number, number];

export type PdfPageTransform = {
  pageIndex: number;
  pdfToRenderMatrix: PdfMatrix;
  renderToPdfMatrix?: PdfMatrix;
};

export type ConfidenceBand = "high" | "medium" | "low";
export type ReviewDisposition = "auto_accepted" | "review_required";

export type ConfidenceDecision = {
  band: ConfidenceBand;
  review_disposition: ReviewDisposition;
  policy_version: "candidate-confidence/1";
  evidence_codes: string[];
};

export type OverlayBox = {
  id: string;
  itemId?: string;
  itemIds?: string[];
  pageIndex?: number;
  bbox: PdfCoordinates;
  rawText?: string;
  candidateNumber?: number;
  showCandidateMarker?: boolean;
  confidenceBand?: ConfidenceBand | null;
  reviewDisposition?: ReviewDisposition | null;
  status?: string | null;
  autoAccepted?: boolean;
};

export type BalloonOverlay = {
  id: string;
  itemId?: string;
  sourceId?: string;
  pageIndex?: number;
  center: [number, number];
  number: number;
  version?: number;
  status?: "active" | "deleted";
  sortOrder?: number;
  anchor?: PdfCoordinates;
  leaderTarget?: [number, number];
  placementStatus?: "placed" | "manual_required";
  collisionFlags?: string[];
  radius?: number;
};

export type PdfViewportLike = {
  width: number;
  height: number;
};

export type PdfRenderTaskLike = {
  promise: Promise<unknown>;
  cancel: () => void;
};

export type PdfPageLike = {
  getViewport: (options: { scale: number }) => PdfViewportLike;
  render: (options: {
    canvasContext: CanvasRenderingContext2D;
    viewport: PdfViewportLike;
  }) => PdfRenderTaskLike;
};

export type PdfDocumentLike = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageLike>;
};

export type CandidateType =
  | "linear_dimension"
  | "diameter_dimension"
  | "thread"
  | "radius"
  | "angle"
  | "general_requirement"
  | "composite";

export type ReviewItem = {
  item_id: string;
  raw_text: string;
  item_type?: CandidateType;
  coarse_type?: string;
  coordinates?: PdfCoordinates | null;
  scope?: "local_feature" | "global_requirement";
  balloon_required?: boolean | null;
  requires_confirmation?: boolean;
  quantity?: number | null;
  nominal?: string | null;
  upper_tolerance?: string | null;
  lower_tolerance?: string | null;
  feature_kind?: "hole" | "shaft" | "cylindrical_feature" | "unknown" | null;
  depth?: string | null;
  through?: boolean | null;
  thread_spec?: string | null;
  thread_depth?: string | null;
  radius_value?: string | null;
  angle_value?: string | null;
  source_location_ids?: string[];
  page_index?: number | null;
  status?: string;
  inspection_item?: string;
  inspection_standard?: string;
  inspection_method?: string;
  key_dimension?: string;
  inspection_role?: string;
  source_page?: number;
  remarks?: string;
  sip_detail_fields_confirmed?: boolean;
  technical_requirement_refs?: string[];
  sip_suggestion_provenance?: Record<string, string>;
  confidence_decision?: ConfidenceDecision;
  acceptance_source?:
    | "confidence_policy"
    | "manual"
    | "manual_override"
    | null;
  active: boolean;
};

export type ReviewCommand =
  | { type: "keep"; item_id: string }
  | { type: "exclude"; item_id: string }
  | { type: "edit"; item_id: string; fields: Record<string, unknown> }
  | {
      type: "add";
      raw_text: string;
      item_type: CandidateType;
      coordinates: PdfCoordinates;
      scope: "local_feature" | "global_requirement";
      balloon_required: boolean;
      page_index?: number;
    }
  | { type: "merge"; item_ids: string[]; raw_text: string }
  | { type: "split"; item_id: string; parts: Array<{ raw_text: string }> }
  | { type: "resolve_confirmation"; item_id: string; accepted: boolean }
  | { type: "set_balloon_required"; item_id: string; balloon_required: boolean }
  | {
      type: "promote_source";
      observation_id: string;
      raw_text: string;
      item_type: CandidateType;
      scope: "local_feature" | "global_requirement";
      balloon_required: boolean;
      page_index: number;
    }
  | { type: "ignore_source"; observation_id: string }
  | { type: "ignore_sources"; observation_ids: string[] }
  | {
      type: "set_sip_detail_fields";
      item_id: string;
      inspection_item: string;
      inspection_standard: string;
      inspection_method: string;
      key_dimension: string;
      inspection_role: string;
      source_page: number;
      remarks: string;
    }
  | {
      type: "set_sip_metadata";
      material_code: string;
      material_name: string;
      drawing_number: string;
      material: string;
      revision: string;
    }
  | {
      type: "set_technical_requirement_match";
      requirement_id: string;
      outcome: "matched_items" | "global_scope" | "excluded";
      matched_item_ids?: string[];
    };

export type TechnicalRequirement = {
  requirement_id: string;
  ordinal?: number | null;
  raw_text: string;
  normalized_text: string;
  source_location_ids: string[];
  page_index: number;
  category:
    | "standalone_check"
    | "applicability_rule"
    | "unsupported"
    | "ambiguous";
  subtype: string;
  parsed_parameters: Record<string, string>;
  match_outcome: "matched_items" | "global_scope" | "unresolved";
  matched_candidate_ids: string[];
  generated_candidate_id?: string | null;
  rule_version: "technical-requirement/1";
  review_required: boolean;
  review_status?: "suggested" | "confirmed" | "excluded";
};

export type ReviewWorkingCopy = {
  id: string;
  project_id: string;
  raw_result_id: string;
  version: number;
  items: ReviewItem[];
  coverage: ReviewCoverage;
  technical_requirements?: TechnicalRequirement[];
  manual_review_count?: number;
  numbering_stale: boolean;
  items_frozen_at: string | null;
  items_frozen_by: string | null;
  items_frozen_version: number | null;
  sip_metadata?: {
    material_code?: string;
    material_name?: string;
    drawing_number?: string;
    material?: string;
    revision?: string;
  };
};

export type ReviewCoverageEntry = {
  observation_id: string;
  source_location_id: string;
  candidate_id?: string | null;
  disposition: string;
  coordinates: PdfCoordinates;
  requires_confirmation: boolean;
};

export type ReviewCoverage = {
  blocking_count?: number;
  review_required_count?: number;
  coverage_checked?: boolean;
  entries?: ReviewCoverageEntry[];
  blocking_observation_ids?: string[];
  relations?: Array<Record<string, unknown>>;
};

export type ProjectWorkbenchPage = {
  page_index: number;
  width: number;
  height: number;
  pdf_to_render_matrix: PdfMatrix;
  render_to_pdf_matrix: PdfMatrix;
};

export type ProjectWorkbenchCandidate = {
  id: string;
  item_id: string;
  page_index: number;
  bbox_pdf: PdfCoordinates;
  confidence_band?: ConfidenceBand | null;
  review_disposition?: ReviewDisposition | null;
  status?: string | null;
};

export type ProjectWorkbenchSource = {
  id: string;
  item_ids: string[];
  page_index: number;
  bbox_pdf: PdfCoordinates;
  raw_text?: string;
};

export type BalloonRecord = {
  id: string;
  project_id: string;
  inspection_item_id: string;
  source_location_id: string;
  page_index: number;
  suggested_number: number;
  formal_number: number | null;
  sort_order: number;
  anchor_bbox_pdf: PdfCoordinates;
  leader_target_pdf: [number, number];
  center_pdf: [number, number];
  placement_status: "placed" | "manual_required";
  collision_flags: string[];
  status: "active" | "deleted";
  version: number;
};

export type ProjectWorkbenchResponse = {
  project: { id: string; state: string; version: number };
  working_copy: ReviewWorkingCopy;
  pages: ProjectWorkbenchPage[];
  candidates: ProjectWorkbenchCandidate[];
  sources: ProjectWorkbenchSource[];
  balloons: BalloonRecord[];
  balloon_blockers: string[];
  source_pdf_url: string;
  reviewed_result_id: string | null;
  latest_export: ExportJob | null;
};

export type ExportArtifactKind = "ballooned_pdf" | "sip_excel" | "manifest";

export type ExportArtifact = {
  kind: ExportArtifactKind;
  sha256?: string;
  size_bytes?: number;
  reviewed_result_id?: string;
  downloadable: boolean;
};

export type ExportJob = {
  id: string;
  project_id: string;
  reviewed_result_id: string;
  status: "pending" | "running" | "success" | "failed";
  error_id?: string | null;
  artifacts: ExportArtifact[];
};

export type ProjectPhase =
  | "queued"
  | "processing"
  | "ready_for_review"
  | "failed";

export type ProcessingStage =
  | "queued"
  | "parsing"
  | "recognizing"
  | "preparing_review";

export type ProjectStatus = {
  project_id?: string;
  phase: ProjectPhase;
  stage?: ProcessingStage | null;
  workbench_ready: boolean;
  retryable: boolean;
  error: {
    code: string;
    stage: string;
  } | null;
};

export type GetJson = <Result>(
  path: string,
  signal?: AbortSignal,
) => Promise<Result>;

export type PostJson = <Result = unknown>(
  path: string,
  body: unknown,
  headers: Record<string, string>,
) => Promise<Result>;

export type PostForm = <Result>(
  path: string,
  body: FormData,
  signal?: AbortSignal,
) => Promise<Result>;
