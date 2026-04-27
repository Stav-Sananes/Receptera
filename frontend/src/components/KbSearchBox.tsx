/**
 * KbSearchBox — manual Hebrew lookup against the knowledge base.
 *
 * The hot path auto-surfaces RAG chunks alongside LLM suggestions. But agents
 * also need to *actively* look something up mid-call ("what's our refund
 * policy again?"). This component sends the query straight to /api/kb/query
 * and renders top-K chunks with similarity scores — no LLM in the loop, no
 * confidence gate, just raw retrieval.
 */

import { useState } from 'react'
import { searchKb, type KbSearchResult } from '../api/kb'

export function KbSearchBox() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KbSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const r = await searchKb(query.trim(), 5)
      setResults(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3">
      <form onSubmit={onSubmit} className="flex gap-2" dir="rtl">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="חפש במאגר הידע..."
          className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm text-right focus:border-blue-400 focus:outline-none"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:bg-gray-300"
        >
          {loading ? '...' : 'חפש'}
        </button>
      </form>

      {error && (
        <p className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700" dir="rtl">
          ⚠ {error}
        </p>
      )}

      {results.length > 0 && (
        <ul className="mt-3 space-y-2">
          {results.map((r) => {
            const sim = parseFloat(r.source.similarity ?? '0')
            const filename = r.source.filename ?? '(unknown)'
            return (
              <li
                key={r.id}
                className="rounded border border-gray-100 bg-gray-50 px-3 py-2"
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs text-gray-500" dir="rtl">
                    {filename}
                  </span>
                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-800">
                    {Math.round(sim * 100)}%
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-gray-800 text-right" dir="rtl">
                  {r.text}
                </p>
              </li>
            )
          })}
        </ul>
      )}

      {!loading && !error && query && results.length === 0 && (
        <p className="mt-2 text-xs text-gray-500" dir="rtl">
          לא נמצאו תוצאות. ודא שיש מסמכים במאגר הידע.
        </p>
      )}
    </div>
  )
}
