export type PdfCoordinates = [number, number, number, number];
export type PdfMatrix = [number, number, number, number, number, number];

export type PdfPageTransform = {
  pageIndex: number;
  pdfToRenderMatrix: PdfMatrix;
};

export type OverlayBox = {
  id: string;
  pageIndex?: number;
  bbox: PdfCoordinates;
};

export type BalloonOverlay = {
  id: string;
  pageIndex?: number;
  center: [number, number];
  number: number;
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
    }
  | { type: "merge"; item_ids: string[]; raw_text: string }
  | { type: "split"; item_id: string; parts: Array<{ raw_text: string }> }
  | { type: "resolve_confirmation"; item_id: string; accepted: boolean }
  | { type: "set_balloon_required"; item_id: string; balloon_required: boolean };

export type ReviewWorkingCopy = {
  id: string;
  project_id: string;
  raw_result_id: string;
  version: number;
  items: ReviewItem[];
  coverage: Record<string, unknown>;
  numbering_stale: boolean;
  items_frozen_at: string | null;
  items_frozen_by: string | null;
  items_frozen_version: number | null;
};

export type PostJson = (
  path: string,
  body: Record<string, unknown>,
  headers: Record<string, string>,
) => Promise<unknown>;
