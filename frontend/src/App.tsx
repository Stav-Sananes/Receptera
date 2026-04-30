/**
 * App — Receptra browser sidebar root (Phase 6).
 *
 * Layout (RTL):
 *   ┌─────────────────────────── StatusBar ─────────────────────────────┐
 *   │  TranscriptPanel  │  SuggestionPanel                              │
 *   └───────────────────────────── KbPanel ─────────────────────────────┘
 *
 * useWebSocket manages the /ws/stt connection + all WS event state.
 * useAudioCapture manages the MediaDevices + AudioWorklet pipeline.
 * The two hooks are composed here — `sendBinary` from useWebSocket
 * flows into useAudioCapture.start().
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { CallSummary } from './api/summary'
import { generateSummary } from './api/summary'
import { HistoryPanel } from './components/HistoryPanel'
import { KbAdminPanel } from './components/KbAdminPanel'
import { KbSearchBox } from './components/KbSearchBox'
import { StatsPanel } from './components/StatsPanel'
import { StatusBar } from './components/StatusBar'
import { SummaryPanel } from './components/SummaryPanel'
import { SuggestionPanel } from './components/SuggestionPanel'
import { TranscriptPanel } from './components/TranscriptPanel'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useCallHistory } from './hooks/useCallHistory'
import { useWebSocket } from './hooks/useWebSocket'

export default function App() {
  const ws = useWebSocket()
  const audio = useAudioCapture()
  const history = useCallHistory()

  const [summary, setSummary] = useState<CallSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  // Stable id for the current in-progress call. Set on Start, cleared on
  // a fresh start so each session gets its own history row.
  const callIdRef = useRef<string | null>(null)
  const callStartRef = useRef<number>(0)

  // Auto-persist the in-progress call to localStorage whenever its
  // contents change (finals, intent, or summary). On the next start,
  // a new id is minted, freezing the previous call as a history entry.
  useEffect(() => {
    if (!callIdRef.current) return
    if (ws.finals.length === 0 && !summary) return
    history.saveCall({
      id: callIdRef.current,
      startedAt: callStartRef.current,
      finals: ws.finals,
      intent: ws.latestIntent,
      summary,
    })
  }, [ws.finals, ws.latestIntent, summary, history])

  const handleStart = useCallback(async () => {
    // Mint a fresh call id — previous call (if any) is already saved
    // to history under its own id.
    callIdRef.current = `call-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    callStartRef.current = Date.now()
    setSummary(null)
    setSummaryError(null)

    // Connect WS first, then open microphone.
    ws.connect()
    await audio.start(ws.sendBinary, () => {
      // WS already connected above; no-op callback.
    })
  }, [ws, audio])

  const handleStop = useCallback(() => {
    audio.stop(ws.disconnect)
  }, [ws, audio])

  const handleEndCall = useCallback(async () => {
    if (ws.finals.length === 0) return
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const result = await generateSummary(ws.finals.map((f) => f.text))
      setSummary(result)
    } catch (err) {
      setSummaryError(err instanceof Error ? err.message : String(err))
    } finally {
      setSummaryLoading(false)
    }
  }, [ws.finals])

  // Auto-end-call: when the agent disconnects (clicked Stop) AND we have
  // finals AND haven't generated a summary yet, fire it automatically.
  // Saves a click for every successful call. The summary still re-runs
  // if the agent clicks the manual button afterwards.
  useEffect(() => {
    if (audio.isCapturing) return
    if (ws.status === 'connected') return
    if (ws.finals.length === 0) return
    if (summary || summaryLoading) return
    void handleEndCall()
  }, [audio.isCapturing, ws.status, ws.finals.length, summary, summaryLoading, handleEndCall])

  const handleCopySummary = useCallback(() => {
    if (!summary) return
    const text = [
      `נושא: ${summary.topic}`,
      summary.key_points.length > 0 ? `פרטים מרכזיים:\n${summary.key_points.map((p) => `• ${p}`).join('\n')}` : '',
      summary.action_items.length > 0 ? `פעולות נדרשות:\n${summary.action_items.map((a) => `• ${a}`).join('\n')}` : '',
    ]
      .filter(Boolean)
      .join('\n\n')
    void navigator.clipboard.writeText(text)
  }, [summary])

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-50" dir="rtl" lang="he">
      <StatusBar
        status={ws.status}
        modelName={ws.modelName}
        isCapturing={audio.isCapturing}
        micError={audio.micError}
        onStart={() => void handleStart()}
        onStop={handleStop}
      />

      {/* Main two-column layout */}
      <div className="grid flex-1 grid-cols-2 gap-3 overflow-hidden p-3">
        <TranscriptPanel
          partialText={ws.partialText}
          finals={ws.finals}
          onEndCall={() => void handleEndCall()}
          latestIntent={ws.latestIntent}
        />
        <SuggestionPanel
          tokenBuffer={ws.tokenBuffer}
          suggestions={ws.suggestions}
          pipelineError={ws.pipelineError}
        />
      </div>

      {/* Post-call summary panel (Feature 3) */}
      {(summary || summaryLoading || summaryError) && (
        <div className="border-t border-gray-200 p-3">
          <SummaryPanel
            summary={summary}
            loading={summaryLoading}
            error={summaryError}
            onCopy={handleCopySummary}
          />
        </div>
      )}

      {/* Manual KB search + operator stats */}
      <div className="border-t border-gray-200 px-3 py-2 space-y-2">
        <KbSearchBox />
        <StatsPanel />
      </div>

      {/* Past calls (localStorage-backed) */}
      {history.calls.length > 0 && (
        <div className="border-t border-gray-200 p-3">
          <HistoryPanel
            calls={history.calls}
            onRemove={history.removeCall}
            onClearAll={history.clearAll}
          />
        </div>
      )}

      {/* KB admin panel (drag-drop, bulk delete, chunk inspector, test query) */}
      <div className="border-t border-gray-200 p-3">
        <KbAdminPanel />
      </div>
    </div>
  )
}
