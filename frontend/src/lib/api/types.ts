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
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface MeResponse {
  username: string;
}

export type MessageStatus = 'done' | 'stopped' | 'error';

export interface Conversation {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationList {
  conversations: Conversation[];
}

export interface StoredMessage {
  id: number;
  role: ChatRole;
  content: string;
  status: MessageStatus;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: StoredMessage[];
}
