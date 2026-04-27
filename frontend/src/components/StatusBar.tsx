/**
 * StatusBar — top bar showing WS connection state + model name (FE-05).
 */

import type { WsStatus } from '../types/ws'

interface Props {
  status: WsStatus
  modelName: string
  isCapturing: boolean
  micError: string | null
  onStart: () => void
  onStop: () => void
}

const STATUS_LABEL: Record<WsStatus, string> = {
  disconnected: 'מנותק',
  connecting: 'מתחבר...',
  connected: 'מחובר',
  error: 'שגיאת חיבור',
}

const STATUS_COLOR: Record<WsStatus, string> = {
  disconnected: 'bg-gray-400',
  connecting: 'bg-yellow-400',
  connected: 'bg-green-500',
  error: 'bg-red-500',
}

export function StatusBar({ status, modelName, isCapturing, micError, onStart, onStop }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-2 shadow-sm">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${STATUS_COLOR[status]}`} />
        <span className="text-sm font-medium text-gray-700">{STATUS_LABEL[status]}</span>
        {modelName && (
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
            {modelName}
          </span>
        )}
      </div>

      <h1 className="text-base font-bold tracking-tight text-gray-900">Receptra</h1>

      <div className="flex items-center gap-2">
        {micError && (
          <span className="text-xs text-red-600" title={micError}>
            ⚠ מיקרופון
          </span>
        )}
        {isCapturing ? (
          <button
            onClick={onStop}
            className="rounded-md bg-red-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-600 active:scale-95"
          >
            עצור
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={status === 'connecting'}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 active:scale-95 disabled:opacity-50"
          >
            התחל שיחה
          </button>
        )}
      </div>
    </header>
  )
}
