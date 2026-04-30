/**
 * SupervisorView — live multi-agent dashboard.
 *
 * Connects to /ws/supervisor on mount, receives an initial snapshot,
 * then live-updates per-agent state from the event stream.
 *
 * Reach this view at:  http://<receptra-host>:5173/?view=supervisor
 */

import { useEffect, useState } from 'react'

interface AgentSnapshot {
  agent_id: string
  connected_at: string
  last_intent: { label: string; label_he: string } | null
  last_intent_at: string | null
  last_final_text: string
  last_final_at: string | null
  n_finals: number
  last_e2e_ms: number | null
}

const INTENT_COLORS: Record<string, string> = {
  booking: 'bg-blue-100 text-blue-800 border-blue-200',
  complaint: 'bg-red-100 text-red-800 border-red-200',
  billing: 'bg-purple-100 text-purple-800 border-purple-200',
  information: 'bg-green-100 text-green-800 border-green-200',
  cancellation: 'bg-orange-100 text-orange-800 border-orange-200',
  other: 'bg-gray-100 text-gray-700 border-gray-200',
}

function _latencyColor(ms: number | null): string {
  if (ms === null) return 'text-gray-400'
  if (ms < 1500) return 'text-green-700'
  if (ms < 2500) return 'text-yellow-700'
  return 'text-red-700'
}

function _fmtRelative(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} דק׳`
  return `${Math.floor(diff / 3_600_000)} שעות`
}

function AgentCard({ agent }: { agent: AgentSnapshot }) {
  const intentColor =
    (agent.last_intent && INTENT_COLORS[agent.last_intent.label]) ?? INTENT_COLORS.other
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-sm font-semibold text-gray-900">{agent.agent_id}</span>
        <span className="inline-flex items-center gap-1 rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
          <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
          לייב
        </span>
      </div>

      {agent.last_intent ? (
        <div className={`mb-2 inline-block rounded border px-2 py-0.5 text-xs ${intentColor}`}>
          {agent.last_intent.label_he}
          <span className="ml-2 text-gray-500">({_fmtRelative(agent.last_intent_at)})</span>
        </div>
      ) : (
        <div className="mb-2 text-xs text-gray-400">טרם זוהתה כוונה</div>
      )}

      <p
        className="mb-3 line-clamp-3 min-h-[3rem] text-sm leading-relaxed text-gray-700 text-right"
        dir="rtl"
      >
        {agent.last_final_text || '(ממתין למשפט ראשון)'}
      </p>

      <div className="grid grid-cols-3 gap-2 border-t border-gray-100 pt-2 text-xs" dir="rtl">
        <div>
          <p className="text-gray-500">משפטים</p>
          <p className="font-semibold text-gray-900">{agent.n_finals}</p>
        </div>
        <div>
          <p className="text-gray-500">סה״כ</p>
          <p className={`font-semibold ${_latencyColor(agent.last_e2e_ms)}`}>
            {agent.last_e2e_ms ? `${agent.last_e2e_ms}ms` : '—'}
          </p>
        </div>
        <div>
          <p className="text-gray-500">פעילות אחרונה</p>
          <p className="font-semibold text-gray-900">{_fmtRelative(agent.last_final_at)}</p>
        </div>
      </div>
    </div>
  )
}

export function SupervisorView() {
  const [agents, setAgents] = useState<Map<string, AgentSnapshot>>(new Map())
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>(
    'connecting',
  )

  useEffect(() => {
    const url = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/supervisor`
    const ws = new WebSocket(url)

    ws.onopen = () => setStatus('connected')
    ws.onclose = () => setStatus('disconnected')
    ws.onerror = () => setStatus('disconnected')

    ws.onmessage = (msg) => {
      const ev = JSON.parse(msg.data as string) as
        | { type: 'snapshot'; agents: AgentSnapshot[] }
        | (Record<string, unknown> & { agent_id?: string })

      if ((ev as { type: string }).type === 'snapshot') {
        const map = new Map<string, AgentSnapshot>()
        for (const a of (ev as { agents: AgentSnapshot[] }).agents) map.set(a.agent_id, a)
        setAgents(map)
        return
      }

      const agent_id = (ev as { agent_id?: string }).agent_id
      if (!agent_id) return

      setAgents((prev) => {
        const next = new Map(prev)
        const cur = next.get(agent_id)
        const t = (ev as { type: string }).type

        if (t === 'agent_connected') {
          next.set(agent_id, {
            agent_id,
            connected_at: new Date().toISOString(),
            last_intent: null,
            last_intent_at: null,
            last_final_text: '',
            last_final_at: null,
            n_finals: 0,
            last_e2e_ms: null,
          })
        } else if (t === 'agent_disconnected') {
          next.delete(agent_id)
        } else if (t === 'utterance_final' && cur) {
          next.set(agent_id, {
            ...cur,
            last_final_text: (ev as { text?: string }).text ?? '',
            last_final_at: new Date().toISOString(),
            n_finals: cur.n_finals + 1,
          })
        } else if (t === 'intent_detected' && cur) {
          next.set(agent_id, {
            ...cur,
            last_intent: {
              label: (ev as { label: string }).label,
              label_he: (ev as { label_he: string }).label_he,
            },
            last_intent_at: new Date().toISOString(),
          })
        } else if (t === 'suggestion_complete' && cur) {
          next.set(agent_id, {
            ...cur,
            last_e2e_ms: (ev as { e2e_latency_ms?: number }).e2e_latency_ms ?? null,
          })
        }
        return next
      })
    }

    return () => ws.close()
  }, [])

  // Re-render every 10s so relative timestamps tick.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 10_000)
    return () => clearInterval(id)
  }, [])

  const agentList = Array.from(agents.values())

  return (
    <div className="min-h-screen bg-gray-50 p-6" dir="rtl" lang="he">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">דשבורד מפקח</h1>
          <p className="text-sm text-gray-500">
            {agentList.length} סוכנים פעילים · חיבור{' '}
            {status === 'connected' ? '✓' : status === 'connecting' ? '...' : '✗'}
          </p>
        </div>
        <a
          href="?"
          className="rounded border border-gray-300 bg-white px-3 py-1 text-sm hover:bg-gray-100"
        >
          חזרה לתצוגת סוכן
        </a>
      </header>

      {agentList.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">
            אין סוכנים מחוברים כעת. סוכן יופיע כאן אוטומטית כשיתחיל שיחה.
          </p>
          <p className="mt-2 text-xs text-gray-400">
            סוכנים מתחברים ב-<code>?agent_id=NAME</code> כדי לקבל זיהוי קבוע
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agentList.map((a) => (
          <AgentCard key={a.agent_id} agent={a} />
        ))}
      </div>
    </div>
  )
}
