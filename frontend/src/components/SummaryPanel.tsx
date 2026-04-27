/**
 * SummaryPanel — post-call Hebrew summary card (Feature 3).
 * Shown after "סיים שיחה" button is clicked and summary returns.
 */
import type { CallSummary } from '../api/summary'

interface Props {
  summary: CallSummary | null
  loading: boolean
  error: string | null
  onCopy: () => void
}

export function SummaryPanel({ summary, loading, error, onCopy }: Props) {
  if (!summary && !loading && !error) return null

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">סיכום שיחה</h3>
        {summary && (
          <button
            onClick={onCopy}
            className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:bg-gray-200"
          >
            העתק
          </button>
        )}
      </div>

      {loading && (
        <p className="text-sm text-gray-400 animate-pulse">מסכם שיחה...</p>
      )}

      {error && (
        <p className="text-sm text-red-600">⚠ {error}</p>
      )}

      {summary && !loading && (
        <div className="space-y-2 text-right" dir="rtl">
          <div>
            <span className="text-xs font-medium text-gray-500">נושא</span>
            <p className="text-sm text-gray-900">{summary.topic}</p>
          </div>
          {summary.key_points.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-500">פרטים מרכזיים</span>
              <ul className="mt-1 list-disc list-inside space-y-0.5">
                {summary.key_points.map((pt, i) => (
                  <li key={i} className="text-sm text-gray-800">{pt}</li>
                ))}
              </ul>
            </div>
          )}
          {summary.action_items.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-500">פעולות נדרשות</span>
              <ul className="mt-1 list-disc list-inside space-y-0.5">
                {summary.action_items.map((item, i) => (
                  <li key={i} className="text-sm text-gray-800">{item}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-gray-400">{summary.total_ms} ms · {summary.model}</p>
        </div>
      )}
    </div>
  )
}
