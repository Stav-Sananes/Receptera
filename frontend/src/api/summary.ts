export interface CallSummary {
  topic: string
  key_points: string[]
  action_items: string[]
  raw_text: string
  model: string
  total_ms: number
}

export async function generateSummary(transcriptLines: string[]): Promise<CallSummary> {
  const res = await fetch('/api/summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript_lines: transcriptLines }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<CallSummary>
}
