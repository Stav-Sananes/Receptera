/**
 * HistoryPanel — shows recent saved calls + lets the agent re-open one.
 *
 * Shown when there's at least one stored call. Each row is collapsed
 * by default; clicking expands the full transcript + summary.
 */

import { useState } from 'react'
import type { StoredCall } from '../hooks/useCallHistory'

interface Props {
  calls: StoredCall[]
  onRemove: (id: string) => void
  onClearAll: () => void
}

const INTENT_COLORS: Record<string, string> = {
  booking: 'bg-blue-100 text-blue-800',
  complaint: 'bg-red-100 text-red-800',
  billing: 'bg-purple-100 text-purple-800',
  information: 'bg-green-100 text-green-800',
  cancellation: 'bg-orange-100 text-orange-800',
  other: 'bg-gray-100 text-gray-700',
}

function _formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleString('he-IL', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function _firstLine(call: StoredCall): string {
  if (call.summary?.topic) return call.summary.topic
  return call.finals[0]?.text?.slice(0, 80) ?? '(שיחה ריקה)'
}

function CallRow({
  call,
  onRemove,
}: {
  call: StoredCall
  onRemove: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-md border border-gray-200 bg-white">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-start justify-between gap-2 px-3 py-2 text-right hover:bg-gray-50"
      >
        <div className="flex-1 min-w-0">
          <p className="truncate text-sm font-medium text-gray-900" dir="rtl">
            {_firstLine(call)}
          </p>
          <p className="text-xs text-gray-500" dir="rtl">
            {_formatTime(call.startedAt)} · {call.finals.length} משפטים
          </p>
        </div>
        {call.intent && (
          <span
            className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${INTENT_COLORS[call.intent.label] ?? INTENT_COLORS.other}`}
          >
            {call.intent.label_he}
          </span>
        )}
      </button>
      {expanded && (
        <div className="border-t border-gray-100 px-3 py-2 space-y-2">
          {call.finals.map((f, i) => (
            <p key={i} className="text-sm leading-relaxed text-gray-800 text-right" dir="rtl">
              {f.text}
            </p>
          ))}
          {call.summary && (
            <div className="mt-3 rounded bg-gray-50 px-2 py-1.5">
              <p className="mb-1 text-xs font-semibold text-gray-600" dir="rtl">
                סיכום
              </p>
              <p className="text-sm text-gray-800 text-right" dir="rtl">
                {call.summary.topic}
              </p>
              {call.summary.action_items.length > 0 && (
                <ul className="mt-1 list-disc pr-5 text-sm text-gray-700" dir="rtl">
                  {call.summary.action_items.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex justify-end pt-1">
            <button
              onClick={() => onRemove(call.id)}
              className="rounded px-2 py-0.5 text-xs text-red-600 hover:bg-red-50"
            >
              מחק
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function HistoryPanel({ calls, onRemove, onClearAll }: Props) {
  if (calls.length === 0) return null

  return (
    <section className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">היסטוריית שיחות ({calls.length})</h2>
        <button
          onClick={() => {
            if (confirm('למחוק את כל ההיסטוריה?')) onClearAll()
          }}
          className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-200"
        >
          נקה הכל
        </button>
      </div>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {calls.map((c) => (
          <CallRow key={c.id} call={c} onRemove={onRemove} />
        ))}
      </div>
    </section>
  )
}
