"""Per-tenant known-recipients store, Phase 3b step-up translation.

A tenant's known recipients are the recipients it has seen or
approved before. A call to a recipient not on the list needs
step-up, even if the binding allows it.

The store is a durable JSON file, so the list survives proxy
restarts. Path from MCP_PROXY_KNOWN_RECIPIENTS_FILE, default
~/.relayshield/known-recipients.json, never /tmp: the Mac reboot
cleared /tmp on 2026-11-04. Format: {"tenant_id": [recipient, ...]}.
Recipients are normalized the same way as _intent_mismatch:
lowercased and stripped. A corrupt or missing file starts empty;
the corrupt case is logged, never fatal. Writes are atomic:
temp file in the same directory, then os.replace.
"""

import json
import logging
import os
import threading

log = logging.getLogger(__name__)

_ENV_VAR = "MCP_PROXY_KNOWN_RECIPIENTS_FILE"
_DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".relayshield", "known-recipients.json")


def _normalize(recipient):
    return str(recipient or "").strip().lower()


class KnownRecipients:
    """Durable per-tenant set of known recipients, JSON-backed."""

    def __init__(self, path=None):
        self._path = os.path.expanduser(path or os.environ.get(_ENV_VAR, "") or _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._known = {}
        self._load()

    @property
    def path(self):
        return self._path

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return
        except Exception as exc:
            log.warning("known-recipients file unreadable, starting empty: %s: %s", self._path, exc)
            return
        if not isinstance(data, dict):
            log.warning("known-recipients file is not a dict, starting empty: %s", self._path)
            return
        for tenant_id, recipients in data.items():
            if not isinstance(recipients, list):
                continue
            self._known[str(tenant_id)] = {_normalize(r) for r in recipients if _normalize(r)}

    def _save_locked(self):
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self._path + ".tmp"
        data = {tid: sorted(recipients) for tid, recipients in self._known.items() if recipients}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
        os.replace(tmp, self._path)

    def is_known(self, tenant_id, recipient):
        tenant = str(tenant_id or "")
        rec = _normalize(recipient)
        if not tenant or not rec:
            return False
        with self._lock:
            return rec in self._known.get(tenant, set())

    def record(self, tenant_id, recipient):
        """Record a recipient as known. Returns True if newly added."""
        tenant = str(tenant_id or "")
        rec = _normalize(recipient)
        if not tenant or not rec:
            return False
        with self._lock:
            known = self._known.setdefault(tenant, set())
            if rec in known:
                return False
            known.add(rec)
            self._save_locked()
            return True
