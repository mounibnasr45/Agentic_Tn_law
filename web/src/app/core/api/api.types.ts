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
}

export interface AskResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
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
