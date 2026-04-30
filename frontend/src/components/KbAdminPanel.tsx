/**
 * KbAdminPanel — full self-service admin for the Hebrew knowledge base.
 *
 * Built for non-technical Israeli call center managers. Replaces and
 * extends the legacy KbPanel:
 *
 *  - Drag-and-drop multi-file upload with progress + per-file error
 *  - Document list with checkboxes, bulk delete, click-to-inspect
 *  - Chunk inspector modal showing the exact text indexed
 *  - KB stats header — doc count, chunk count, total bytes, freshness
 *  - Inline test query (sanity check after upload)
 *
 * Not in scope here: tenant namespaces (separate phase).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  bulkDelete,
  deleteDocument,
  getDocumentChunks,
  getKbHealth,
  getKbStats,
  listDocuments,
  searchKb,
  uploadDocument,
  type KbChunkRow,
  type KbSearchResult,
  type KbStats,
} from '../api/kb'
import type { KbDocument, KbHealth } from '../types/kb'

const ACCEPT_RE = /\.(md|txt|pdf|docx)$/i

function _fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

function _fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('he-IL', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── Stats header ──────────────────────────────────────────────────────────────

function StatsHeader({ stats, health }: { stats: KbStats | null; health: KbHealth | null }) {
  if (!stats || !health) return null
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-4 py-3 bg-gray-50 border-b border-gray-100">
      <div>
        <p className="text-xs text-gray-500" dir="rtl">מסמכים</p>
        <p className="text-lg font-semibold text-gray-900">{stats.n_documents}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500" dir="rtl">מקטעים</p>
        <p className="text-lg font-semibold text-gray-900">{stats.n_chunks}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500" dir="rtl">גודל</p>
        <p className="text-lg font-semibold text-gray-900">{_fmtBytes(stats.total_bytes)}</p>
      </div>
      <div>
        <p className="text-xs text-gray-500" dir="rtl">עדכון אחרון</p>
        <p className="text-sm font-medium text-gray-900">{_fmtDate(stats.newest_ingest)}</p>
      </div>
    </div>
  )
}

// ── Drop zone ─────────────────────────────────────────────────────────────────

function DropZone({
  onFiles,
  uploading,
  errors,
}: {
  onFiles: (files: File[]) => void
  uploading: boolean
  errors: string[]
}) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const submit = (filelist: FileList | null) => {
    if (!filelist) return
    const files = Array.from(filelist).filter((f) => ACCEPT_RE.test(f.name))
    if (files.length > 0) onFiles(files)
  }

  return (
    <div className="px-4 py-3">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          submit(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${
          dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <p className="text-sm text-gray-600" dir="rtl">
          {uploading
            ? 'מעלה...'
            : 'גרור קבצים או לחץ להעלאה (.md / .txt / .pdf / .docx — מרובים נתמכים)'}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.txt,.pdf,.docx"
          multiple
          className="hidden"
          onChange={(e) => {
            submit(e.target.files)
            if (inputRef.current) inputRef.current.value = ''
          }}
        />
      </div>
      {errors.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {errors.map((err, i) => (
            <li key={i} className="text-xs text-red-700" dir="rtl">
              ⚠ {err}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Chunk inspector modal ─────────────────────────────────────────────────────

function ChunkInspector({
  filename,
  onClose,
}: {
  filename: string | null
  onClose: () => void
}) {
  const [chunks, setChunks] = useState<KbChunkRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!filename) return
    setLoading(true)
    setError(null)
    getDocumentChunks(filename)
      .then(setChunks)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [filename])

  if (!filename) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-3xl overflow-hidden rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <h3 className="text-sm font-semibold text-gray-800" dir="rtl">
            מקטעי "{filename}" ({chunks.length})
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-800 text-lg">
            ×
          </button>
        </div>
        <div className="overflow-y-auto px-4 py-3 space-y-2 max-h-[70vh]">
          {loading && <p className="text-sm text-gray-500">טוען...</p>}
          {error && <p className="text-sm text-red-700">⚠ {error}</p>}
          {chunks.map((c) => (
            <div key={c.id} className="rounded border border-gray-100 bg-gray-50 px-3 py-2">
              <p className="mb-1 text-xs text-gray-500" dir="rtl">
                #{c.chunk_index} · {c.id.slice(0, 16)}
              </p>
              <p
                className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap text-right"
                dir="rtl"
              >
                {c.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Inline test query ─────────────────────────────────────────────────────────

function TestQuery() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<KbSearchResult[] | null>(null)
  const [loading, setLoading] = useState(false)

  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!q.trim()) return
    setLoading(true)
    try {
      setResults(await searchKb(q.trim(), 3))
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <details className="border-t border-gray-100 px-4 py-2">
      <summary className="cursor-pointer text-sm font-medium text-gray-700" dir="rtl">
        בדיקת שאילתה (sanity check)
      </summary>
      <form onSubmit={run} className="mt-2 flex gap-2" dir="rtl">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='נסה: "מה שעות הפתיחה?"'
          className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm text-right"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-gray-700 px-3 py-1 text-sm text-white hover:bg-gray-900 disabled:bg-gray-300"
        >
          בדוק
        </button>
      </form>
      {results !== null && (
        <ul className="mt-2 space-y-1">
          {results.length === 0 && (
            <li className="text-xs text-gray-500" dir="rtl">
              לא נמצאו תוצאות
            </li>
          )}
          {results.map((r) => {
            const sim = parseFloat(r.source.similarity ?? '0')
            return (
              <li key={r.id} className="rounded bg-gray-50 px-2 py-1 text-xs" dir="rtl">
                <span className="font-medium text-blue-700">{Math.round(sim * 100)}%</span>{' '}
                <span className="text-gray-500">{r.source.filename}:</span>{' '}
                <span className="text-gray-800">{r.text.slice(0, 80)}…</span>
              </li>
            )
          })}
        </ul>
      )}
    </details>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

function HealthBadge({ service, status }: { service: string; status: string }) {
  const ok = status === 'ok'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${
        ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`} />
      {service}: {status}
    </span>
  )
}

export function KbAdminPanel() {
  const [docs, setDocs] = useState<KbDocument[]>([])
  const [stats, setStats] = useState<KbStats | null>(null)
  const [health, setHealth] = useState<KbHealth | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadErrors, setUploadErrors] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [inspectFilename, setInspectFilename] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [d, s, h] = await Promise.all([listDocuments(), getKbStats(), getKbHealth()])
      setDocs(d)
      setStats(s)
      setHealth(h)
    } catch {
      // backend may be down — silent
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = setInterval(() => void refresh(), 30_000)
    return () => clearInterval(id)
  }, [refresh])

  const handleUpload = useCallback(
    async (files: File[]) => {
      setUploading(true)
      setUploadErrors([])
      const errs: string[] = []
      for (const f of files) {
        try {
          await uploadDocument(f)
        } catch (e) {
          errs.push(`${f.name}: ${e instanceof Error ? e.message : String(e)}`)
        }
      }
      setUploadErrors(errs)
      setUploading(false)
      await refresh()
    },
    [refresh],
  )

  const toggle = (filename: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(filename)) next.delete(filename)
      else next.add(filename)
      return next
    })
  }

  const toggleAll = () => {
    setSelected((prev) => (prev.size === docs.length ? new Set() : new Set(docs.map((d) => d.filename))))
  }

  const handleBulkDelete = async () => {
    if (selected.size === 0) return
    if (!confirm(`למחוק ${selected.size} מסמכים?`)) return
    try {
      await bulkDelete(Array.from(selected))
      setSelected(new Set())
      await refresh()
    } catch {
      // ignore
    }
  }

  const handleDeleteOne = async (filename: string) => {
    if (!confirm(`מחק את "${filename}"?`)) return
    try {
      await deleteDocument(filename)
      await refresh()
    } catch {
      // ignore
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <h2 className="text-sm font-semibold text-gray-700">ניהול בסיס ידע</h2>
        {health && (
          <div className="flex gap-2">
            <HealthBadge service="ChromaDB" status={health.chroma} />
            <HealthBadge service="BGE-M3" status={health.ollama} />
          </div>
        )}
      </div>

      <StatsHeader stats={stats} health={health} />
      <DropZone onFiles={handleUpload} uploading={uploading} errors={uploadErrors} />

      {/* Bulk actions toolbar */}
      {docs.length > 0 && (
        <div className="flex items-center justify-between px-4 py-1.5 border-b border-gray-100 bg-gray-50">
          <label className="flex items-center gap-2 text-xs text-gray-700" dir="rtl">
            <input
              type="checkbox"
              checked={selected.size === docs.length && docs.length > 0}
              onChange={toggleAll}
            />
            {selected.size > 0 ? `${selected.size} נבחרו` : 'בחר הכל'}
          </label>
          {selected.size > 0 && (
            <button
              onClick={() => void handleBulkDelete()}
              className="rounded bg-red-600 px-2 py-0.5 text-xs text-white hover:bg-red-700"
            >
              מחק ({selected.size})
            </button>
          )}
        </div>
      )}

      {/* Document list */}
      {docs.length > 0 && (
        <ul className="divide-y divide-gray-100">
          {docs.map((doc) => (
            <li key={doc.filename} className="flex items-center gap-3 px-4 py-2">
              <input
                type="checkbox"
                checked={selected.has(doc.filename)}
                onChange={() => toggle(doc.filename)}
              />
              <button
                onClick={() => setInspectFilename(doc.filename)}
                className="flex-1 text-right hover:underline"
                dir="rtl"
              >
                <span className="text-sm font-medium text-gray-800">{doc.filename}</span>
                <span className="mr-2 text-xs text-gray-400">
                  {doc.chunk_count} מקטעים · {_fmtDate(doc.ingested_at_iso)}
                </span>
              </button>
              <button
                onClick={() => void handleDeleteOne(doc.filename)}
                className="text-xs text-red-500 hover:text-red-700"
              >
                מחק
              </button>
            </li>
          ))}
        </ul>
      )}

      {docs.length === 0 && health && (
        <p className="px-4 py-3 text-xs text-gray-400" dir="rtl">
          אין מסמכים בבסיס הידע. גרור קובץ למעלה כדי להתחיל.
        </p>
      )}

      <TestQuery />

      <ChunkInspector
        filename={inspectFilename}
        onClose={() => setInspectFilename(null)}
      />
    </section>
  )
}
