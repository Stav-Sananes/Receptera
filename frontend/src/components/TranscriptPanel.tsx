/**
 * TranscriptPanel — live Hebrew transcript display (FE-02).
 *
 * Shows:
 * - Completed utterances (final events) stacked top-to-bottom
 * - Current partial transcript with a blinking cursor
 * - STT latency badge on each final
 */

import { useEffect, useRef } from 'react'
import type { FinalTranscript, IntentDetected } from '../types/ws'

const INTENT_COLORS: Record<string, string> = {
  booking:      'bg-blue-100 text-blue-800',
  complaint:    'bg-red-100 text-red-800',
  billing:      'bg-purple-100 text-purple-800',
  information:  'bg-green-100 text-green-800',
  cancellation: 'bg-orange-100 text-orange-800',
  other:        'bg-gray-100 text-gray-700',
}

interface Props {
  partialText: string
  finals: FinalTranscript[]
  onEndCall?: () => void
  /** Most recent intent classification (v1.1 F4). */
  latestIntent?: IntentDetected | null
}

function LatencyBadge({ ms }: { ms: number }) {
  const color = ms < 500 ? 'bg-green-100 text-green-800' : ms < 1000 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
  return (
    <span className={`mr-2 rounded px-1.5 py-0.5 text-xs font-mono ${color}`}>
      STT {ms} ms
    </span>
  )
}

export function TranscriptPanel({ partialText, finals, onEndCall, latestIntent }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [finals.length, partialText])

  return (
    <section className="flex h-full flex-col rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <h2 className="text-sm font-semibold text-gray-700">תמלול</h2>
        {latestIntent && (
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${INTENT_COLORS[latestIntent.label] ?? INTENT_COLORS.other}`}
            title={latestIntent.label}
          >
            {latestIntent.label_he}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {finals.length === 0 && !partialText && (
          <p className="text-sm text-gray-400">ממתין לדיבור...</p>
        )}
        {finals.map((f, i) => (
          <div key={i} className="rounded-md bg-gray-50 px-3 py-2">
            <p className="text-sm leading-relaxed text-gray-900 text-right" dir="rtl">
              {f.text}
            </p>
            <div className="mt-1 flex justify-end">
              <LatencyBadge ms={f.stt_latency_ms} />
              <span className="text-xs text-gray-400">{f.duration_ms} ms שמע</span>
            </div>
          </div>
        ))}
        {partialText && (
          <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
            <p className="text-sm leading-relaxed text-blue-800 text-right" dir="rtl">
              {partialText}
              <span className="ml-1 animate-pulse">|</span>
            </p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {finals.length > 0 && onEndCall && (
        <div className="border-t border-gray-100 px-4 py-2">
          <button
            onClick={onEndCall}
            className="mt-2 w-full rounded bg-gray-700 px-3 py-1.5 text-xs text-white hover:bg-gray-900"
          >
            סיים שיחה וצור סיכום
          </button>
        </div>
      )}
    </section>
  )
}
