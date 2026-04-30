/**
 * WebhookPanel — collapsed config status + test button for the CRM webhook.
 *
 * Webhook URL/secret are set on the backend via env vars (RECEPTRA_WEBHOOK_URL,
 * RECEPTRA_WEBHOOK_SECRET). UI only reflects whether they are configured —
 * the secret never crosses to the browser.
 */

import { useEffect, useState } from 'react'
import { getWebhookStatus, testWebhook, type WebhookStatus } from '../api/webhooks'

export function WebhookPanel() {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<WebhookStatus | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; reason: string } | null>(null)

  useEffect(() => {
    if (!open) return
    getWebhookStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [open])

  const runTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await testWebhook()
      setTestResult(r)
    } catch (e) {
      setTestResult({ ok: false, reason: e instanceof Error ? e.message : String(e) })
    } finally {
      setTesting(false)
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-right hover:bg-gray-50"
      >
        <span className="text-sm font-semibold text-gray-700">CRM Webhook</span>
        <span className="text-xs text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="border-t border-gray-100 p-3 space-y-2 text-sm" dir="rtl">
          {!status && <p className="text-gray-500">טוען...</p>}
          {status && !status.configured && (
            <div className="rounded bg-yellow-50 px-2 py-1.5 text-yellow-800">
              ⚠ Webhook לא מוגדר. הגדר{' '}
              <code className="bg-yellow-100 px-1 rounded">RECEPTRA_WEBHOOK_URL</code> ב-env.
            </div>
          )}
          {status?.configured && (
            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">יעד:</span>
                <span className="font-mono text-xs text-gray-800">{status.url_host}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">חתימה (HMAC):</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-xs ${
                    status.signed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}
                >
                  {status.signed ? 'מופעלת' : 'מבוטלת'}
                </span>
              </div>
              <button
                onClick={() => void runTest()}
                disabled={testing}
                className="mt-2 w-full rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:bg-gray-300"
              >
                {testing ? 'שולח...' : 'שלח payload בדיקה'}
              </button>
              {testResult && (
                <p
                  className={`mt-1 rounded px-2 py-1 text-xs ${
                    testResult.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
                  }`}
                >
                  {testResult.ok ? '✓ נשלח בהצלחה' : `✗ ${testResult.reason}`}
                </p>
              )}
            </div>
          )}
          <p className="text-xs text-gray-500 mt-2">
            לאחר כל סיכום שיחה, Receptra ישלח JSON ל-URL זה (intent + summary + finals).
            התחבר ל-Make/Zapier/n8n או CRM משלך.
          </p>
        </div>
      )}
    </section>
  )
}
