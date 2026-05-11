// Mirrors the Pydantic schemas in services/api/schemas.py and the
// FinalDossier produced by the synthesizer. Keep these in sync by hand —
// later phases can codegen from OpenAPI.

export type ResearchStance = "positive" | "neutral" | "negative";

export type ThesisStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type ThesisCreateRequest = {
  ticker: string;
  focus_question?: string | null;
};

export type ThesisCreateResponse = {
  thesis_id: string;
  status: string;
};

export type CitedStatement = {
  statement: string;
  cited_chunk_ids: string[];
};

export type FinalDossier = {
  executive_summary: string;
  executive_summary_cited_chunk_ids: string[];
  research_stance: ResearchStance;
  evidence_strength: number;
  bull_case: CitedStatement[];
  bear_case: CitedStatement[];
  catalysts: CitedStatement[];
  key_risks: CitedStatement[];
  disconfirming_evidence: CitedStatement[];
  macro_context: string | null;
  macro_context_cited_chunk_ids: string[];
  valuation_summary: string | null;
  valuation_summary_cited_chunk_ids: string[];
  quant_summary: string | null;
  limitations: string[];
  analyst_disclaimer: string;
  notes: string | null;
};

export type ThesisGetResponse = {
  thesis_id: string;
  ticker: string;
  focus_question: string | null;
  status: ThesisStatus;
  research_stance: ResearchStance | null;
  evidence_strength: number | null;
  dossier: FinalDossier | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type ChunkSnippet = {
  chunk_id: string;
  source_id: string;
  text: string;
  source_kind: string | null;
  source_provider: string | null;
  source_url: string | null;
  source_title: string | null;
};

export type CitationListItem = {
  id: string;
  section: string;
  claim: string;
  chunk_ids: string[];
  confidence: number | null;
  supporting_chunks: ChunkSnippet[];
  created_at: string;
};

export type CitationListResponse = {
  citations: CitationListItem[];
};

export type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  status: "ok" | "warn" | "error";
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AuditListResponse = {
  events: AuditEvent[];
  total: number;
};
