/**
 * useWebSocket — manages the /ws/stt WebSocket connection + event state (Phase 6 FE-01).
 *
 * Returned state:
 *   status        — 'disconnected' | 'connecting' | 'connected' | 'error'
 *   modelName     — from SttReady event (shown in StatusBar)
 *   partialText   — latest PartialTranscript.text (typewriter preview)
 *   finals        — completed FinalTranscript[] (append-only during a session)
 *   tokenBuffer   — accumulated LLM token deltas for typewriter rendering
 *   suggestions   — last SuggestionComplete event (null until first arrives)
 *   pipelineError — last SuggestionError | SttError (null on success)
 *   sendBinary    — send a binary frame to the WS (used by useAudioCapture)
 *   connect       — open the WS
 *   disconnect    — close the WS and reset state
 */

import { useCallback, useRef, useState } from 'react'
import type {
  FinalTranscript,
  SuggestionComplete,
  SuggestionError,
  SttError,
  WsEvent,
  WsStatus,
} from '../types/ws'

const WS_URL =
  typeof window !== 'undefined'
    ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/stt`
    : 'ws://localhost:5173/ws/stt'

export interface WsState {
  status: WsStatus
  modelName: string
  partialText: string
  finals: FinalTranscript[]
  tokenBuffer: string
  suggestions: SuggestionComplete | null
  pipelineError: SuggestionError | SttError | null
  sendBinary: (data: ArrayBuffer) => void
  connect: () => void
  disconnect: () => void
}

export function useWebSocket(): WsState {
  const wsRef = useRef<WebSocket | null>(null)

  const [status, setStatus] = useState<WsStatus>('disconnected')
  const [modelName, setModelName] = useState('')
  const [partialText, setPartialText] = useState('')
  const [finals, setFinals] = useState<FinalTranscript[]>([])
  const [tokenBuffer, setTokenBuffer] = useState('')
  const [suggestions, setSuggestions] = useState<SuggestionComplete | null>(null)
  const [pipelineError, setPipelineError] = useState<SuggestionError | SttError | null>(null)

  const disconnect = useCallback(() => {
    const ws = wsRef.current
    if (ws) {
      ws.onclose = null // suppress auto-reconnect
      ws.close()
      wsRef.current = null
    }
    setStatus('disconnected')
    setPartialText('')
    setTokenBuffer('')
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) return

    setStatus('connecting')
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
    }

    ws.onmessage = (evt) => {
      let event: WsEvent
      try {
        event = JSON.parse(evt.data as string) as WsEvent
      } catch {
        return
      }

      switch (event.type) {
        case 'ready':
          setModelName(event.model)
          break
        case 'partial':
          setPartialText(event.text)
          break
        case 'final':
          setPartialText('')
          setFinals((prev) => [...prev, event])
          // Reset suggestion state for new utterance
          setTokenBuffer('')
          setSuggestions(null)
          setPipelineError(null)
          break
        case 'error':
          setPipelineError(event)
          break
        case 'suggestion_token':
          setTokenBuffer((prev) => prev + event.delta)
          break
        case 'suggestion_complete':
          setSuggestions(event)
          setTokenBuffer('') // final replaces stream
          break
        case 'suggestion_error':
          setPipelineError(event)
          break
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }

    ws.onclose = () => {
      setStatus('disconnected')
      wsRef.current = null
    }
  }, [])

  const sendBinary = useCallback((data: ArrayBuffer) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  }, [])

  return {
    status,
    modelName,
    partialText,
    finals,
    tokenBuffer,
    suggestions,
    pipelineError,
    sendBinary,
    connect,
    disconnect,
  }
}
