/**
 * Fetch wrappers for /api/kb/* endpoints (Phase 4 HTTP contract).
 * All functions throw on non-2xx responses with the parsed KbErrorResponse body.
 */

import type { IngestResult, KbDocument, KbHealth } from '../types/kb'

const BASE = '/api/kb'

async function _unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // ignore parse error
    }
    throw new Error(`HTTP ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

/** Upload a .md or .txt file to the KB. */
export async function uploadDocument(file: File): Promise<IngestResult> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: fd })
  return _unwrap<IngestResult>(res)
}

/** Ingest raw text content (filename + body). */
export async function ingestText(filename: string, content: string): Promise<IngestResult> {
  const res = await fetch(`${BASE}/ingest-text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content }),
  })
  return _unwrap<IngestResult>(res)
}

/** List all ingested documents. */
export async function listDocuments(): Promise<KbDocument[]> {
  const res = await fetch(`${BASE}/documents`)
  return _unwrap<KbDocument[]>(res)
}

/** Delete a document by filename. */
export async function deleteDocument(filename: string): Promise<{ deleted: number }> {
  const res = await fetch(`${BASE}/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
  return _unwrap<{ deleted: number }>(res)
}

/** KB health check. */
export async function getKbHealth(): Promise<KbHealth> {
  const res = await fetch(`${BASE}/health`)
  return _unwrap<KbHealth>(res)
}
