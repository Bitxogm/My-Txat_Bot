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
