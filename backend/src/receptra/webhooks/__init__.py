"""Outbound CRM webhook (v1.2).

After every successful POST /api/summary, the sender fires one HTTP POST
to ``settings.webhook_url`` carrying the structured call payload. Designed
to bridge Receptra to existing CRM/automation tools (Make, Zapier, n8n,
custom Salesforce/HubSpot) without Receptra becoming a cloud service.

Privacy thesis: webhook is OFF by default (empty webhook_url). When ON,
the operator explicitly chose a destination — no implicit outbound traffic.

PII boundary: structured logs record outcome (status code, attempt count,
duration) but NEVER the body. The body itself contains Hebrew transcript
text and is the operator's responsibility once it leaves the host.
"""
