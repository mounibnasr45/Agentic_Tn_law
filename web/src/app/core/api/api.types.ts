/**
 * Wire types — a byte-for-byte mirror of the Pydantic schemas in `app/api/schemas/`.
 *
 * These stay snake_case ON PURPOSE. They describe what the API actually sends, not what
 * reads nicely in TypeScript. Renaming here would mean every field silently arrives as
 * `undefined` the day the two drift apart, and `undefined` in a citation is a legal
 * citation that renders blank rather than an error anyone notices.
 *
 * Dates arrive as ISO 8601 strings (Pydantic serialises `datetime`), and UUIDs as strings.
 * Both are typed as `string` here and parsed at the point of use.
 */

// ---------------------------------------------------------------------------
// Auth  <- app/api/schemas/auth.py
// ---------------------------------------------------------------------------

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  /** Seconds until the ACCESS token expires — not the refresh token. */
  expires_in: number;
}

export interface User {
  id: string;
  email: string;
  /**
   * Drives whether the admin navigation renders. NOT a security control — the boundary is
   * get_current_admin() in app/api/deps.py, re-checked on every admin request. This only
   * stops a non-admin being shown a link that would 403.
   */
  is_admin: boolean;
}

export interface Credentials {
  email: string;
  password: string;
}

// ---------------------------------------------------------------------------
// Chat  <- app/api/schemas/chat.py + app/api/schemas/conversation.py
// ---------------------------------------------------------------------------

/**
 * A citation backed by a real `chunks` row.
 *
 * Bug 4 in this project's history was that `sources` was a hardcoded placeholder string.
 * Every field below exists because the API can no longer return a citation it did not
 * actually retrieve — `excerpt` is the chunk's content truncated to 400 chars server-side.
 */
export interface Citation {
  chunk_id: number;
  source: string;
  /** null for text that is not under a numbered article, e.g. the preamble. */
  article_number: string | null;
  score: number;
  rank: number;
  excerpt: string;
}

export interface AskRequest {
  question: string;
  /** null starts a new thread; a UUID continues an existing one. */
  conversation_id: string | null;
  /** Which language the ANSWER is written in. Cited articles stay French either way. */
  language: 'fr' | 'en';
}

export interface AskResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  trace: AgentTrace;
}

export interface ConversationSummary {
  id: string;
  /** Backend derives this from the first question (truncated to 120 chars). */
  title: string | null;
  created_at: string;
  updated_at: string;
}

export type MessageRole = 'user' | 'assistant';

export interface MessageResponse {
  role: MessageRole;
  content: string;
  /** Only populated for assistant messages. */
  latency_ms: number | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Search  <- app/api/routes/search.py
// ---------------------------------------------------------------------------

/** Mirrors `FusionStrategy` in app/domain/retrieval.py. */
export type FusionStrategy = 'weighted' | 'rrf';

export interface SearchResponse {
  query: string;
  /** What the retriever actually did — "hybrid", "semantic", "lexical", or "none". */
  retrieval_type: string;
  results: Citation[];
}

// ---------------------------------------------------------------------------
// Health  <- app/api/schemas/common.py
// ---------------------------------------------------------------------------

export interface HealthResponse {
  /** "ok" only when the database is reachable AND the corpus has been ingested. */
  status: string;
  database: boolean;
  model_loaded: boolean;
  embedding_model: string;
  corpus_chunks: number;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** Every DomainError surfaces through FastAPI in this shape. */
export interface ApiErrorBody {
  detail: string;
}

// ---------------------------------------------------------------------------
// Validation constraints
// ---------------------------------------------------------------------------

/**
 * Mirrors the Pydantic `Field(...)` bounds so the forms can give instant feedback.
 *
 * The server validates again and its answer is the one that counts — these exist purely to
 * save the user a round trip, never to be trusted.
 */
export const CONSTRAINTS = {
  /** RegisterRequest.password — 12, because length dominates entropy. */
  password: { minLength: 12, maxLength: 128 },
  /** AskRequest.question */
  question: { minLength: 3, maxLength: 2000 },
} as const;

// ---------------------------------------------------------------------------
// Admin  <- app/api/schemas/admin.py
// ---------------------------------------------------------------------------

/** pending -> processing -> indexed | failed */
export type DocumentStatus = 'pending' | 'processing' | 'indexed' | 'failed';

export interface AdminDocument {
  id: string;
  title: string;
  status: DocumentStatus;
  chunks_total: number;
  chunks_done: number;
  corpus_version: number;
  error: string | null;
  created_at: string;
  indexed_at: string | null;
  /**
   * 0..1, computed SERVER-side. Dividing chunks_done by chunks_total here would produce
   * NaN for every document in "pending" (chunks_total is 0 until chunking finishes), and
   * every document passes through pending.
   */
  progress: number;
}

export interface CorpusStatus {
  documents: AdminDocument[];
  total_chunks: number;
  embedding_model: string;
  /** True while any document is still pending or processing — drives the poll loop. */
  is_ingesting: boolean;
}

export interface UploadAccepted {
  document: AdminDocument;
  /** False when the bytes were already indexed with the current encoder. */
  processing: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  /** Total user-authored messages ever sent — an activity figure, not today's count. */
  message_count: number;
  /** Active (non-revoked, non-expired) refresh tokens — roughly one per signed-in device. */
  session_count: number;
}

// ---------------------------------------------------------------------------
// Agent trace  <- app/api/schemas/conversation.py
// ---------------------------------------------------------------------------

export interface TraceResult {
  article_number: string | null;
  score: number;
  rank: number;
}

export interface TraceStep {
  kind: 'retrieval' | 'reflection' | 'answer';
  label: string;
  /** The query the AGENT composed — usually not the sentence the user typed. */
  query: string | null;
  results: TraceResult[];
  detail: string | null;
}

export interface AgentTrace {
  steps: TraceStep[];
  iterations_used: number;
  max_iterations: number;
  /** True when the reflection checkpoint caught an undefined legal term and re-retrieved. */
  regrounded: boolean;
}

// ---------------------------------------------------------------------------
// Chat streaming  <- POST /api/ask/stream, app/api/routes/chat.py
// ---------------------------------------------------------------------------

/**
 * NDJSON, one of these per line. `step` arrives the instant the agent records it — the
 * whole reason this endpoint exists instead of just POSTing to /ask — `final` carries
 * exactly what /ask returns in one shot, and `error` is a run-time failure that arrives
 * in-band because the HTTP status (200) is already committed by the time the agent can
 * fail (see app/services/chat_service.py's stream_answer docstring).
 */
export type ChatStreamEvent =
  | { event: 'step'; data: TraceStep }
  | { event: 'final'; data: AskResponse }
  | { event: 'error'; data: { message: string } };

// ---------------------------------------------------------------------------
// Evaluation  <- app/api/schemas/evaluation.py
// ---------------------------------------------------------------------------

export interface AblationArm {
  name: string;
  arm: 'dense' | 'hybrid' | 'lexical' | 'rrf';
  hit_at_1: number;
  hit_at_3: number;
  hit_at_5: number;
  hit_at_10: number;
  mrr: number;
  ndcg_at_10: number;
}

export interface GoldenSetInfo {
  questions: number;
  sources: string[];
  /** 1/questions — the honest error bar on every metric on the page. */
  one_question_worth: number;
}

export interface EncoderComparison {
  before_model: string;
  before_max_tokens: number;
  before_hit_at_1: number;
  before_hit_at_5: number;
  before_mrr: number;
  after_model: string;
  after_max_tokens: number;
  after_hit_at_1: number;
  after_hit_at_5: number;
  after_mrr: number;
  truncated_chunks: number;
  total_chunks: number;
  dropped_token_pct: number;
}

export interface EvaluationResponse {
  model: string;
  corpus_chunks: number;
  arms: AblationArm[];
  best_arm: string;
  deployed_weight_bm25: number;
  golden_set: GoldenSetInfo;
  encoder_fix: EncoderComparison;
}

// ---------------------------------------------------------------------------
// Documents  <- app/api/schemas/documents.py
// ---------------------------------------------------------------------------

export interface CorpusDocument {
  id: string;
  title: string;
  size_bytes: number;
  /** Chunks derived from this document — how much of it the agent can actually cite. */
  chunk_count: number;
  indexed_at: string | null;
}
