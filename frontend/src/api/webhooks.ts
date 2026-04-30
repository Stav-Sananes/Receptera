/**
 * Webhook config API — read-only status + manual test trigger.
 * The actual URL/secret is set via env vars on the backend (RECEPTRA_WEBHOOK_*).
 * UI only shows whether they're configured, not the values.
 */

export interface WebhookStatus {
  configured: boolean
  signed: boolean
  url_host: string
}

export async function getWebhookStatus(): Promise<WebhookStatus> {
  const res = await fetch('/api/webhooks/status')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<WebhookStatus>
}

export interface WebhookTestResult {
  ok: boolean
  reason: string
}

export async function testWebhook(): Promise<WebhookTestResult> {
  const res = await fetch('/api/webhooks/test', { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<WebhookTestResult>
}
