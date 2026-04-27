/**
 * StatsPanel — operator dashboard powered by GET /api/audit/stats.
 *
 * Collapsed by default to keep agent UI clean. Click "סטטיסטיקות" to expand.
 * Auto-refreshes every 15s while expanded.
 */

import { useEffect, useState } from 'react'
import { getAuditStats, type AuditStats, type StatsWindow } from '../api/audit'

function _fmt(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  return `${Math.round(ms)} ms`
}

function _color(ms: number | null): string {
  if (ms === null) return 'text-gray-500'
  if (ms < 1000) return 'text-green-700'
  if (ms < 2000) return 'text-yellow-700'
  return 'text-red-700'
}

function WindowBlock({ w, title }: { w: StatsWindow | null; title: string }) {
  if (!w) {
    return (
      <div className="rounded border border-gray-100 px-3 py-2">
        <h3 className="text-xs font-semibold text-gray-500" dir="rtl">
          {title}
        </h3>
        <p className="text-xs text-gray-400">אין נתונים</p>
      </div>
    )
  }
  return (
    <div className="rounded border border-gray-100 px-3 py-2 space-y-1">
      <h3 className="text-xs font-semibold text-gray-500" dir="rtl">
        {title}
      </h3>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs" dir="rtl">
        <span className="text-gray-500">משפטים:</span>
        <span className="font-medium text-gray-900">{w.n_utterances}</span>
        <span className="text-gray-500">הצעות:</span>
        <span className="font-medium text-gray-900">{w.n_pipeline_runs}</span>
        <span className="text-gray-500">STT ממוצע:</span>
        <span className={`font-medium ${_color(w.avg_stt_latency_ms)}`}>
          {_fmt(w.avg_stt_latency_ms)}
        </span>
        <span className="text-gray-500">STT p95:</span>
        <span className={`font-medium ${_color(w.p95_stt_latency_ms)}`}>
          {_fmt(w.p95_stt_latency_ms)}
        </span>
        <span className="text-gray-500">סה״כ ממוצע:</span>
        <span className={`font-medium ${_color(w.avg_e2e_latency_ms)}`}>
          {_fmt(w.avg_e2e_latency_ms)}
        </span>
        <span className="text-gray-500">סה״כ p95:</span>
        <span className={`font-medium ${_color(w.p95_e2e_latency_ms)}`}>
          {_fmt(w.p95_e2e_latency_ms)}
        </span>
        <span className="text-gray-500">RAG ירוד:</span>
        <span className="font-medium text-gray-900">
          {Math.round(w.pct_rag_degraded * 100)}%
        </span>
      </div>
    </div>
  )
}

export function StatsPanel() {
  const [open, setOpen] = useState(false)
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const tick = async () => {
      try {
        const s = await getAuditStats()
        if (!cancelled) setStats(s)
        if (!cancelled) setError(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void tick()
    const id = window.setInterval(tick, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [open])

  return (
    <section className="rounded-lg border border-gray-200 bg-white">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-right hover:bg-gray-50"
      >
        <span className="text-sm font-semibold text-gray-700">סטטיסטיקות מערכת</span>
        <span className="text-xs text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t border-gray-100 p-3 space-y-2">
          {error && (
            <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-700" dir="rtl">
              ⚠ {error}
            </p>
          )}
          {!stats && !error && <p className="text-xs text-gray-400">טוען...</p>}
          {stats && (
            <>
              <WindowBlock w={stats.all_time} title="כל הזמן" />
              <WindowBlock w={stats.last_24h} title="24 שעות אחרונות" />
            </>
          )}
        </div>
      )}
    </section>
  )
}
