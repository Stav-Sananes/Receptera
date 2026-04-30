"""Supervisor — live multi-agent dashboard (v1.2 #3).

In-process pub/sub bus. Each /ws/stt connection publishes lifecycle events
(agent_connected, utterance_final, intent_detected, call_summary,
agent_disconnected). Each /ws/supervisor connection subscribes and receives
all events from all currently connected agents.

Architecture:
    Agent A   ─┐
    Agent B   ─┼─→ EventBus.publish() ─→ Supervisor 1
    Agent C   ─┘                       └→ Supervisor 2 (same data, multicast)

Single-process only. Multi-host setups need Redis pub/sub or NATS — out of
scope for v1.2 (Receptra runs on one Mac).

Privacy: supervisor sees the same Hebrew transcripts the agent does.
Authentication is OUT OF SCOPE — supervisor endpoint MUST be reachable only
from trusted networks (loopback or VPN). README documents this.
"""
