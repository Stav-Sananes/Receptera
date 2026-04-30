export interface CallSummary {
  topic: string
  key_points: string[]
  action_items: string[]
  raw_text: string
  model: string
  total_ms: number
}

export interface FinalMeta {
  text: string
  duration_ms: number
  stt_latency_ms: number
}

export interface IntentMeta {
  label: string
  label_he: string
}

export interface SummaryRequest {
  transcript_lines: string[]
  /** v1.2 webhook context — optional, all backward-compatible. */
  call_id?: string
  finals_meta?: FinalMeta[]
  intent?: IntentMeta
}

/** @deprecated use generateSummaryV2 with webhook context. Kept for back-compat. */
export async function generateSummary(transcriptLines: string[]): Promise<CallSummary> {
  return generateSummaryV2({ transcript_lines: transcriptLines })
}

export async function generateSummaryV2(req: SummaryRequest): Promise<CallSummary> {
  const res = await fetch('/api/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<CallSummary>
}
