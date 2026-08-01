import type { components } from "./generated";


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
  components["schemas"]["Add"]["item_type"];

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
  sip_mapping_exceptions?: string[];
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
  components["schemas"]["ReviewCommandRequest"]["command"];

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

export type ReviewWorkingCopyTransport =
  components["schemas"]["ReviewWorkingCopyResponse"];

export type ReviewLockResponse =
  components["schemas"]["ReviewLockResponse"];

export type ReviewLockReleaseResponse =
  components["schemas"]["ReviewLockReleaseResponse"];

export type ReviewedResultResponse =
  components["schemas"]["ReviewedResultResponse"];

type ReviewWorkingCopyProjectionTransport =
  components["schemas"]["ReviewWorkingCopyProjection"];

// UI view: narrows opaque JSON records and permits incomplete local fixtures.
// API clients must receive ReviewWorkingCopyTransport before adapting to this view.
export type ReviewWorkingCopyView = Omit<
  ReviewWorkingCopyProjectionTransport,
  | "items"
  | "coverage"
  | "technical_requirements"
  | "sip_metadata"
  | "manual_review_count"
> & {
  items: ReviewItem[];
  coverage: ReviewCoverage;
  technical_requirements?: TechnicalRequirement[];
  manual_review_count?: number;
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

export type ProjectWorkbenchPage =
  components["schemas"]["ProjectWorkbenchPageResponse"];

type ProjectWorkbenchCandidateTransport =
  components["schemas"]["ProjectWorkbenchCandidateResponse"];

export type ProjectWorkbenchCandidateView = Omit<
  ProjectWorkbenchCandidateTransport,
  "confidence_band" | "review_disposition" | "status"
> & {
  confidence_band?: ConfidenceBand | null;
  review_disposition?: ReviewDisposition | null;
  status?: string | null;
};

type ProjectWorkbenchSourceTransport =
  components["schemas"]["ProjectWorkbenchSourceResponse"];

export type ProjectWorkbenchSourceView = Omit<
  ProjectWorkbenchSourceTransport,
  "raw_text" | "source_type"
> & {
  raw_text?: string;
  source_type?: string;
};

export type BalloonRecord =
  components["schemas"]["BalloonResponse"];

export type ProjectWorkbenchTransport =
  components["schemas"]["ProjectWorkbenchResponse"];

export type ProjectWorkbenchSipMetadataSuggestion =
  components["schemas"]["ProjectWorkbenchSipMetadataSuggestionResponse"];

export type ProjectWorkbenchView = Omit<
  ProjectWorkbenchTransport,
  "working_copy" | "candidates" | "sources"
> & {
  working_copy: ReviewWorkingCopyView;
  candidates: ProjectWorkbenchCandidateView[];
  sources: ProjectWorkbenchSourceView[];
};

export type ExportArtifactKind =
  components["schemas"]["ExportArtifactResponse"]["kind"];

export type ExportArtifact =
  components["schemas"]["ExportArtifactResponse"];

export type ExportJob =
  components["schemas"]["ExportResponse"];

export type ProjectPhase =
  components["schemas"]["ProjectPhase"];

export type ProcessingStage =
  components["schemas"]["ProcessingStage"];

export type ProjectStatus =
  components["schemas"]["ProjectStatusResponse"];

export type ProjectListTransport =
  components["schemas"]["ProjectListResponse"];

export type ProjectListItemTransport =
  components["schemas"]["ProjectListItemResponse"];

export type RecognitionPreview =
  components["schemas"]["RecognitionPreviewResponse"];

export type GetJson = <Result>(
  path: string,
  signal?: AbortSignal,
) => Promise<Result>;

export type PostJson = <Result = unknown>(
  path: string,
  body: unknown,
  headers: Record<string, string>,
  signal?: AbortSignal,
) => Promise<Result>;

export type PostForm = <Result>(
  path: string,
  body: FormData,
  signal?: AbortSignal,
) => Promise<Result>;
