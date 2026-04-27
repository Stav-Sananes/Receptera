/**
 * TypeScript mirror of receptra.rag.schema Pydantic models.
 * Phase 4 KB HTTP wire contract.
 */

export interface IngestResult {
  filename: string
  chunks_added: number
  chunks_replaced: number
  bytes_ingested: number
}

export interface KbDocument {
  filename: string
  chunk_count: number
  ingested_at_iso: string
}

export interface KbHealth {
  chroma: string
  ollama: string
  collection_count: number
}

export interface KbErrorResponse {
  code: string
  detail: string
}
