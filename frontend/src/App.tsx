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

import { useCallback, useState } from 'react'
import type { CallSummary } from './api/summary'
import { generateSummary } from './api/summary'
import { KbPanel } from './components/KbPanel'
import { StatusBar } from './components/StatusBar'
import { SummaryPanel } from './components/SummaryPanel'
import { SuggestionPanel } from './components/SuggestionPanel'
import { TranscriptPanel } from './components/TranscriptPanel'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useWebSocket } from './hooks/useWebSocket'

export default function App() {
  const ws = useWebSocket()
  const audio = useAudioCapture()

  const [summary, setSummary] = useState<CallSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const handleStart = useCallback(async () => {
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

      {/* KB management panel (collapsible) */}
      <div className="border-t border-gray-200 p-3">
        <KbPanel />
      </div>
    </div>
  )
}
