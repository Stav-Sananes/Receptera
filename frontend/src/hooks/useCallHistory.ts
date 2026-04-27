/**
 * useCallHistory — localStorage-backed past-call store.
 *
 * Receptra is a co-pilot for live calls. Without persistence, refreshing
 * the tab wipes everything an agent just did. This hook keeps the last
 * `MAX_CALLS` calls — each containing the finals, the most recent intent,
 * and the post-call summary if one was generated.
 *
 * Storage:
 *   key:  receptra:calls:v1
 *   shape: StoredCall[] (newest first)
 *   cap:  20 calls (older ones drop)
 *
 * Privacy: this is plain localStorage — Hebrew transcripts are PII. The
 * "Clear history" button wipes the key in one click.
 */

import { useCallback, useEffect, useState } from 'react'
import type { CallSummary } from '../api/summary'
import type { FinalTranscript, IntentDetected } from '../types/ws'

export interface StoredCall {
  id: string
  startedAt: number // ms epoch
  finals: FinalTranscript[]
  intent: IntentDetected | null
  summary: CallSummary | null
}

const STORAGE_KEY = 'receptra:calls:v1'
const MAX_CALLS = 20

function _read(): StoredCall[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as StoredCall[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function _write(calls: StoredCall[]): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(calls.slice(0, MAX_CALLS)))
  } catch {
    // quota exceeded or storage disabled — fail soft
  }
}

export interface UseCallHistory {
  calls: StoredCall[]
  /** Save (or update by id) the in-progress call. Newest goes to position 0. */
  saveCall: (call: StoredCall) => void
  /** Drop a single call by id. */
  removeCall: (id: string) => void
  /** Wipe all stored history. */
  clearAll: () => void
}

export function useCallHistory(): UseCallHistory {
  const [calls, setCalls] = useState<StoredCall[]>(() => _read())

  // Keep state in sync if another tab modifies localStorage.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setCalls(_read())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const saveCall = useCallback((call: StoredCall) => {
    setCalls((prev) => {
      const filtered = prev.filter((c) => c.id !== call.id)
      const next = [call, ...filtered].slice(0, MAX_CALLS)
      _write(next)
      return next
    })
  }, [])

  const removeCall = useCallback((id: string) => {
    setCalls((prev) => {
      const next = prev.filter((c) => c.id !== id)
      _write(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    setCalls([])
    _write([])
  }, [])

  return { calls, saveCall, removeCall, clearAll }
}
