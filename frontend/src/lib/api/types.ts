// Mirrors the backend contract in docs/architecture.md ("API de chat").

export interface HealthResponse {
  status: 'ok';
  ollama: 'up' | 'down';
}

export interface ModelInfo {
  name: string;
  size_bytes: number;
  family: string | null;
  parameter_size: string | null;
  quantization: string | null;
  /** Runs on a third-party service: messages leave the local network. */
  remote: boolean;
  /** Accepts images. */
  vision: boolean;
  /** "ollama" or the name of an OpenAI-compatible provider (groq, lmstudio...). */
  provider: string;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string | null;
}

export type ChatRole = 'system' | 'user' | 'assistant';

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  model?: string;
  messages: ChatMessage[];
}

export interface ChatResult {
  model: string;
  content: string;
  /** Id of the saved reply (persistent chat only). */
  messageId?: number | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface MeResponse {
  username: string;
}

export type MessageStatus = 'done' | 'stopped' | 'error';

/** Snapshot of the personality a conversation was created with (read-only). */
export interface PersonalityRef {
  /** null if that personality has since been deleted. */
  id: string | null;
  name: string;
  icon: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  /** null for conversations created before personalities existed. */
  personality: PersonalityRef | null;
}

export interface ConversationList {
  conversations: Conversation[];
}

export type AttachmentKind = 'text' | 'pdf' | 'image';

/** A file as listed on a stored message. */
export interface MessageAttachment {
  id: string;
  filename: string;
  kind: AttachmentKind;
  size_bytes: number;
  /** Only part of its text reached the model. */
  truncated: boolean;
}

/** A file uploaded to a conversation; `sent: false` until a message carries it. */
export interface Attachment extends MessageAttachment {
  mime: string;
  sent: boolean;
  created_at: string;
}

export interface AttachmentList {
  attachments: Attachment[];
}

export type FeedbackRating = 1 | -1;

export type FeedbackReason =
  'incorrect' | 'wrong_command' | 'incomplete' | 'too_long' | 'off_personality' | 'other';

/** The rating of an assistant reply (ADR-024). 👍 carries no reasons or correction. */
export interface MessageFeedback {
  rating: FeedbackRating;
  reasons: FeedbackReason[];
  correction: string | null;
}

/** A rating with the copy of the turn taken when it was saved. */
export interface Feedback extends MessageFeedback {
  message_id: number;
  conversation_id: string;
  question: string;
  question_files: string[];
  answer: string;
  model: string;
  /** The reply predates per-reply models: this is the conversation's last model. */
  model_approximate: boolean;
  provider: string | null;
  personality: string | null;
  /** null = unknown. */
  base_prompt_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackPage {
  items: Feedback[];
  total: number;
}

export interface FeedbackFilters {
  rating?: FeedbackRating;
  model?: string;
  personality?: string;
  reason?: FeedbackReason;
  /** YYYY-MM-DD, UTC, inclusive. */
  from?: string;
  to?: string;
  conversation_id?: string;
}

export interface StoredMessage {
  id: number;
  role: ChatRole;
  content: string;
  status: MessageStatus;
  created_at: string;
  attachments: MessageAttachment[];
  /** Only on assistant replies that were rated. */
  feedback?: MessageFeedback | null;
}

export interface ConversationDetail extends Conversation {
  messages: StoredMessage[];
}

export interface Personality {
  id: string;
  name: string;
  /** lucide icon name, e.g. "flag". */
  icon: string;
  description: string;
  system_prompt: string;
  temperature: number | null;
  top_p: number | null;
  num_ctx: number | null;
  default_model: string | null;
  builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface PersonalityList {
  personalities: Personality[];
}

/** Editable fields. null parameters mean "use the model's default". */
export interface PersonalityInput {
  name: string;
  icon: string;
  description: string;
  system_prompt: string;
  temperature: number | null;
  top_p: number | null;
  num_ctx: number | null;
  default_model: string | null;
}

export type OsintCategory =
  | 'breach'
  | 'username'
  | 'domain'
  | 'image'
  | 'code'
  | 'forum'
  | 'browser_fingerprint'
  | 'aggregator';

export interface OsintSource {
  id: string;
  name: string;
  url: string;
  category: OsintCategory;
  description: string;
  requires_api_key: boolean;
  requires_payment: boolean;
  builtin: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OsintSourceList {
  sources: OsintSource[];
}

export interface OsintSourceInput {
  name: string;
  url: string;
  category: OsintCategory;
  description: string;
  requires_api_key: boolean;
  requires_payment: boolean;
  is_active: boolean;
}
