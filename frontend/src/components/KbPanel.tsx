/**
 * KbPanel — Knowledge Base management UI (FE-06).
 *
 * Features:
 * - File upload (.md / .txt) with drag-and-drop
 * - Document list with chunk count + delete
 * - KB health status (ChromaDB + Ollama BGE-M3)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteDocument, getKbHealth, listDocuments, uploadDocument } from '../api/kb'
import type { KbDocument, KbHealth } from '../types/kb'

function HealthBadge({ service, status }: { service: string; status: string }) {
  const ok = status === 'ok'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium ${ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`} />
      {service}: {status}
    </span>
  )
}

export function KbPanel() {
  const [documents, setDocuments] = useState<KbDocument[]>([])
  const [health, setHealth] = useState<KbHealth | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      const [docs, h] = await Promise.all([listDocuments(), getKbHealth()])
      setDocuments(docs)
      setHealth(h)
    } catch {
      // ignore — backend may be down
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = setInterval(() => void refresh(), 30_000)
    return () => clearInterval(id)
  }, [refresh])

  const handleUpload = useCallback(
    async (file: File) => {
      if (!file.name.match(/\.(md|txt|pdf|docx)$/i)) {
        setUploadError('רק קבצי .md, .txt, .pdf ו-.docx נתמכים')
        return
      }
      setUploading(true)
      setUploadError(null)
      try {
        await uploadDocument(file)
        await refresh()
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : String(err))
      } finally {
        setUploading(false)
      }
    },
    [refresh],
  )

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void handleUpload(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) void handleUpload(file)
  }

  const handleDelete = async (filename: string) => {
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
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2">
        <h2 className="text-sm font-semibold text-gray-700">בסיס ידע</h2>
        {health && (
          <div className="flex gap-2">
            <HealthBadge service="ChromaDB" status={health.chroma} />
            <HealthBadge service="BGE-M3" status={health.ollama} />
            <span className="text-xs text-gray-400">{health.collection_count} מקטעים</span>
          </div>
        )}
      </div>

      {/* Upload zone */}
      <div className="px-4 py-3">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`cursor-pointer rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}`}
        >
          <p className="text-sm text-gray-500">
            {uploading ? 'מעלה...' : 'גרור קובץ או לחץ להעלאה (.md / .txt / .pdf / .docx)'}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.txt,.pdf,.docx"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
        {uploadError && (
          <p className="mt-1 text-xs text-red-600">{uploadError}</p>
        )}
      </div>

      {/* Document list */}
      {documents.length > 0 && (
        <ul className="divide-y divide-gray-100 px-4 pb-3">
          {documents.map((doc) => (
            <li key={doc.filename} className="flex items-center justify-between py-2">
              <div>
                <span className="text-sm font-medium text-gray-800">{doc.filename}</span>
                <span className="mr-2 text-xs text-gray-400">{doc.chunk_count} מקטעים</span>
              </div>
              <button
                onClick={() => void handleDelete(doc.filename)}
                className="text-xs text-red-500 hover:text-red-700"
              >
                מחק
              </button>
            </li>
          ))}
        </ul>
      )}

      {documents.length === 0 && health && (
        <p className="px-4 pb-3 text-xs text-gray-400">אין מסמכים בבסיס הידע</p>
      )}
    </section>
  )
}
