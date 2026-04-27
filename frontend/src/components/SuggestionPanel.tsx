/**
 * SuggestionPanel — typewriter LLM token stream + structured suggestion cards (FE-03, FE-04).
 *
 * Lifecycle per utterance:
 *   1. FinalTranscript received → panel resets (tokenBuffer='', suggestions=null)
 *   2. suggestion_token events → tokenBuffer grows (typewriter rendering)
 *   3. suggestion_complete → structured Suggestion[] cards replace stream
 *   4. suggestion_error → warning badge (non-blocking; cards may still arrive)
 */

import type { SuggestionComplete, SuggestionError, SttError } from '../types/ws'

interface Props {
  tokenBuffer: string
  suggestions: SuggestionComplete | null
  pipelineError: SuggestionError | SttError | null
}

function ConfidencePip({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const color = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <span className="flex items-center gap-1 text-xs text-gray-500">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      {pct}%
    </span>
  )
}

function SuggestionCard({
  text,
  confidence,
  citation_ids,
  index,
}: {
  text: string
  confidence: number
  citation_ids: string[]
  index: number
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm hover:border-blue-300 hover:shadow-md transition-all">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium text-gray-400">הצעה {index + 1}</span>
        <ConfidencePip confidence={confidence} />
      </div>
      <p className="text-sm leading-relaxed text-gray-900 text-right" dir="rtl">
        {text}
      </p>
      {citation_ids.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1 justify-end">
          {citation_ids.map((id) => (
            <span
              key={id}
              className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600"
              title={id}
            >
              ⬗ {id.slice(0, 8)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function LatencyRow({ label, ms }: { label: string; ms: number }) {
  return (
    <span className="text-xs text-gray-400">
      {label}: {ms} ms
    </span>
  )
}

export function SuggestionPanel({ tokenBuffer, suggestions, pipelineError }: Props) {
  const hasStream = tokenBuffer.length > 0
  const hasSuggestions = suggestions !== null

  return (
    <section className="flex h-full flex-col rounded-lg border border-gray-200 bg-white">
      <h2 className="border-b border-gray-100 px-4 py-2 text-sm font-semibold text-gray-700">
        הצעות
      </h2>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {!hasStream && !hasSuggestions && !pipelineError && (
          <p className="text-sm text-gray-400">ממתין לתמלול...</p>
        )}

        {/* Typewriter stream */}
        {hasStream && !hasSuggestions && (
          <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
            <p className="text-sm leading-relaxed text-blue-900 text-right whitespace-pre-wrap" dir="rtl">
              {tokenBuffer}
              <span className="ml-1 animate-pulse">▌</span>
            </p>
          </div>
        )}

        {/* Error badge (non-blocking) */}
        {pipelineError && (
          <div className="rounded-md border border-orange-200 bg-orange-50 px-3 py-2">
            <p className="text-xs text-orange-700">
              ⚠{' '}
              {'code' in pipelineError && 'detail' in pipelineError
                ? `${pipelineError.code}: ${pipelineError.detail}`
                : 'code' in pipelineError && 'message' in pipelineError
                  ? `${pipelineError.code}: ${pipelineError.message}`
                  : JSON.stringify(pipelineError)}
            </p>
          </div>
        )}

        {/* Structured suggestion cards */}
        {hasSuggestions && (
          <>
            {suggestions.suggestions.map((s, i) => (
              <SuggestionCard
                key={i}
                text={s.text}
                confidence={s.confidence}
                citation_ids={s.citation_ids}
                index={i}
              />
            ))}

            {/* Latency breakdown */}
            <div className="flex flex-wrap gap-3 border-t border-gray-100 pt-2">
              <LatencyRow label="RAG" ms={suggestions.rag_latency_ms} />
              <LatencyRow label="TTFT" ms={suggestions.ttft_ms} />
              <LatencyRow label="LLM" ms={suggestions.total_ms} />
              <LatencyRow label="סה״כ" ms={suggestions.e2e_latency_ms} />
              <span className="text-xs text-gray-400">מודל: {suggestions.model}</span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
