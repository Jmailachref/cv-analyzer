// The engine's /v1 API. The web app is served by the API itself, which lets it in
// without a key when OPEN_CLIENT is set (docker compose does).

export type Skill = { name: string; priority: number };

export type Criterion = {
  id: string;
  label: string;
  terms: string[];
  default_synonyms: boolean;
  points_present: number;
  points_absent: number;
};

export type GridSettings = { penalty_cap: number; auto_weight: number; manual_cap: number };

export type OfferSummary = { external_ref: string; title: string; documents: number; updated_at: string };

export type Offer = {
  external_ref: string;
  title: string;
  skills: Skill[];
  grid_version: number;
  criteria: Criterion[];
  settings: GridSettings;
  created_at: string;
  updated_at: string;
};

export type OfferIn = {
  title: string;
  skills: Skill[];
  criteria?: Criterion[] | null;
  settings?: GridSettings;
};

export type DocumentStatus = "queued" | "processing" | "ready" | "unreadable" | "failed";

export type DocumentOut = {
  id: string;
  offer_ref: string;
  external_ref: string | null;
  filename: string;
  size: number;
  status: DocumentStatus;
  error: string | null;
  ocr_used: boolean;
  pages: number | null;
  created_at: string;
  processed_at: string | null;
};

export type Line = {
  n: number;
  page: number;
  section: string;
  text: string;
  start: number;
  end: number;
  bbox: number[] | null;
};

export type DocumentDetail = DocumentOut & { text: string | null; lines: Line[] };

export type Box = { page: number; x0: number; top: number; x1: number; bottom: number };

export type Highlight = {
  id: string;
  document_id: string;
  author_ref: string;
  start: number;
  end: number;
  quote: string;
  boxes: Box[];
  points: number;
  comment: string | null;
  created_at: string;
};

export type HighlightIn = {
  author_ref: string;
  points: number;
  comment?: string | null;
  quote?: string;
  page?: number;
  line?: number;
  boxes?: Box[];
};

export type CriterionResult = {
  id: string;
  label: string;
  found: boolean;
  points: number;
  lines: number[];
  matched_terms: string[];
};

export type Analysis = {
  id: string;
  document_id: string;
  offer_ref: string;
  grid_version: number;
  analyzer: string;
  analyzer_version: string;
  score: number;
  details: { base?: number; penalties?: number; penalties_applied?: number; criteria?: CriterionResult[] };
  created_at: string;
};

export type Score = {
  document_id: string;
  offer_ref: string;
  external_ref: string | null;
  grid_version: number | null;
  auto: number | null;
  manual: number | null;
  final: number | null;
  manual_points: number;
  settings: GridSettings;
  analysis: Analysis | null;
  highlights: Highlight[];
};

export type RankingRow = {
  rank: number | null;
  document_id: string;
  external_ref: string | null;
  filename: string;
  status: DocumentStatus;
  auto: number | null;
  manual: number | null;
  final: number | null;
  missing: string[];
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const response = await fetch(path, init);
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(response.status, error.code ?? "error", error.message ?? response.statusText);
  }
  return data as T;
}

const ref = (value: string) => encodeURIComponent(value);

export const api = {
  offers: () => call<OfferSummary[]>("GET", "/v1/offers"),
  offer: (offerRef: string) => call<Offer>("GET", `/v1/offers/${ref(offerRef)}`),
  saveOffer: (offerRef: string, body: OfferIn) => call<Offer>("PUT", `/v1/offers/${ref(offerRef)}`, body),
  deleteOffer: (offerRef: string) => call<void>("DELETE", `/v1/offers/${ref(offerRef)}`),
  ranking: (offerRef: string) => call<RankingRow[]>("GET", `/v1/offers/${ref(offerRef)}/ranking`),

  upload: (offerRef: string, file: File, externalRef?: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("offer_ref", offerRef);
    if (externalRef) form.append("external_ref", externalRef);
    return call<DocumentOut>("POST", "/v1/documents", form);
  },
  document: (id: string) => call<DocumentDetail>("GET", `/v1/documents/${id}`),
  documentFile: (id: string) => `/v1/documents/${id}/file`,
  deleteDocument: (id: string) => call<void>("DELETE", `/v1/documents/${id}`),
  score: (id: string) => call<Score>("GET", `/v1/documents/${id}/score`),
  addHighlight: (id: string, body: HighlightIn) => call<Highlight>("POST", `/v1/documents/${id}/highlights`, body),
  deleteHighlight: (id: string) => call<void>("DELETE", `/v1/highlights/${id}`),
};

export const PRIORITIES: Record<number, string> = {
  1: "Essentielle",
  2: "Importante",
  3: "Secondaire",
  4: "CV seulement",
  5: "Bonus",
};

export const STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "En attente",
  processing: "Lecture",
  ready: "Lu",
  unreadable: "Illisible",
  failed: "Erreur",
};
