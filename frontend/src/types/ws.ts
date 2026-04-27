/**
 * TypeScript mirror of receptra.stt.events + receptra.pipeline.events Python schemas.
 * Phase 5 WS wire contract — frozen discriminated union on `type` field.
 */

// --- STT events ---

export interface SttReady {
  type: 'ready'
  model: string
  sample_rate: number
  frame_bytes: number
}

export interface PartialTranscript {
  type: 'partial'
  text: string
  t_speech_start_ms: number
  t_emit_ms: number
}

export interface FinalTranscript {
  type: 'final'
  text: string
  t_speech_start_ms: number
  t_speech_end_ms: number
  stt_latency_ms: number
  duration_ms: number
}

export interface SttError {
  type: 'error'
  code: 'model_error' | 'vad_error' | 'protocol_error'
  message: string
}

// --- Pipeline events ---

export interface SuggestionToken {
  type: 'suggestion_token'
  delta: string
}

export interface Suggestion {
  text: string
  confidence: number
  citation_ids: string[]
}

export interface SuggestionComplete {
  type: 'suggestion_complete'
  suggestions: Suggestion[]
  ttft_ms: number
  total_ms: number
  model: string
  rag_latency_ms: number
  e2e_latency_ms: number
}

export interface SuggestionError {
  type: 'suggestion_error'
  code: string
  detail: string
}

export type WsEvent =
  | SttReady
  | PartialTranscript
  | FinalTranscript
  | SttError
  | SuggestionToken
  | SuggestionComplete
  | SuggestionError

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
