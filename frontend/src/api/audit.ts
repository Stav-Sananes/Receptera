/**
 * Operator audit stats — pulls counts + latency aggregates from
 * GET /api/audit/stats. PII-safe: response is numbers only, no transcripts.
 */

export interface StatsWindow {
  label: string
  n_utterances: number
  n_pipeline_runs: number
  avg_stt_latency_ms: number | null
  p95_stt_latency_ms: number | null
  avg_e2e_latency_ms: number | null
  p95_e2e_latency_ms: number | null
  pct_rag_degraded: number
  pct_low_confidence: number | null
}

export interface AuditStats {
  all_time: StatsWindow
  last_24h: StatsWindow | null
}

export async function getAuditStats(): Promise<AuditStats> {
  const res = await fetch('/api/audit/stats')
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
  return res.json() as Promise<AuditStats>
}
