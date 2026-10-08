"""Quarantine management for poisoned MCP servers.

A quarantined server's tool calls are blocked (fail-closed) until an
operator clears it. Quarantine is per-server: other servers keep working.
"""

import json
import logging
import time
import urllib.request

from .neighbor import CLEAN, QUARANTINED

log = logging.getLogger(__name__)


class QuarantineManager:
    """Decides and enforces per-server quarantine."""

    def __init__(self, registry, alert_webhook: str = "",
                 auto_quarantine_after: int = 3):
        self.registry = registry
        self.alert_webhook = (alert_webhook or "").strip()
        self.auto_quarantine_after = auto_quarantine_after
        self.events = []  # quarantine / clear event log

    def is_quarantined(self, url: str) -> bool:
        rep = self.registry.get(url)
        return rep is not None and rep.reputation == QUARANTINED

    def evaluate(self, url: str) -> bool:
        """Auto-quarantine a server that reached the flag threshold.

        Returns True if the server was quarantined by this call.
        """
        rep = self.registry.get(url)
        if rep is None or rep.reputation == QUARANTINED:
            return False
        if len(rep.flags) >= self.auto_quarantine_after:
            self.quarantine(
                url,
                f"auto-quarantine: {len(rep.flags)} flags reached threshold "
                f"of {self.auto_quarantine_after}",
            )
            return True
        return False

    def quarantine(self, url: str, reason: str) -> dict:
        """Quarantine a server immediately (fail-closed from now on)."""
        rep = self.registry.get(url) or self.registry.register(url)
        rep.reputation = QUARANTINED
        event = {"ts": time.time(), "action": "quarantined", "url": url,
                 "reason": reason, "flag_count": len(rep.flags)}
        self.events.append(event)
        log.warning(json.dumps({"event": "server_quarantined", **event}))
        self._send_alert("server_quarantined", event)
        return event

    def clear(self, url: str, cleared_by: str = "operator") -> bool:
        """Clear a quarantine, returning the server to clean.

        Flag history is kept for audit; only the reputation resets.
        Returns False if the server was unknown.
        """
        rep = self.registry.get(url)
        if rep is None:
            return False
        rep.reputation = CLEAN
        event = {"ts": time.time(), "action": "cleared", "url": url,
                 "cleared_by": cleared_by,
                 "prior_flag_count": len(rep.flags)}
        self.events.append(event)
        log.info(json.dumps({"event": "server_quarantine_cleared", **event}))
        self._send_alert("server_quarantine_cleared", event)
        return True

    def _send_alert(self, alert_type: str, event: dict):
        """POST an alert to the configured webhook. Never raises."""
        if not self.alert_webhook:
            return
        try:
            payload = json.dumps(
                {"alert": alert_type, "source": "mcp-proxy", **event}
            ).encode("utf-8")
            req = urllib.request.Request(
                self.alert_webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as exc:
            log.warning("alert webhook failed: %s", exc)
