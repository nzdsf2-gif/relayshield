"""Per-tenant server-to-server credentials store, Phase 3b.

A credential never resolves a tenant. It is selected BY
the session's tenant, and it authenticates the proxy to
the other side. The console is the source of truth: keys
are provisioned there, and the proxy's local file is its
mirror, populated by the sync endpoint and read on every
use. A local file, rather than console-only storage, is
the redundancy Andrew chose: the keys are not only in
the console, so a console outage does not lock the proxy
out of its own credentials.

The file is a durable JSON file, so the keys survive
proxy restarts. Path from MCP_PROXY_TENANT_SECRETS_FILE,
default ~/.relayshield/tenant-secrets.json, never /tmp.
Format: {"tenant_id": {"policy_key": "...",
"screener_key": "...", "collector_secret": "..."}}.
A corrupt or missing file starts empty; the corrupt case
is logged, never fatal. Writes are atomic: temp file in
the same directory, then os.replace.
"""

import json
import logging
import os
import threading

log = logging.getLogger(__name__)

_ENV_VAR = "MCP_PROXY_TENANT_SECRETS_FILE"
_DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".relayshield", "tenant-secrets.json")
_KINDS = ("policy_key", "screener_key", "collector_secret")


class TenantSecrets:
    """Durable per-tenant credential store, JSON-backed."""

    def __init__(self, path=None):
        self._path = os.path.expanduser(path or os.environ.get(_ENV_VAR, "") or _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._secrets = {}
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
            log.warning("tenant-secrets file unreadable, starting empty: %s: %s", self._path, exc)
            return
        if not isinstance(data, dict):
            log.warning("tenant-secrets file is not a dict, starting empty: %s", self._path)
            return
        for tenant_id, kinds in data.items():
            if not isinstance(kinds, dict):
                continue
            kept = {}
            for kind, value in kinds.items():
                if kind in _KINDS and str(value or "").strip():
                    kept[kind] = str(value).strip()
            if kept:
                self._secrets[str(tenant_id)] = kept

    def _save_locked(self):
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self._path + ".tmp"
        data = {tid: dict(kinds) for tid, kinds in self._secrets.items() if kinds}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
        os.replace(tmp, self._path)

    def get(self, tenant_id, kind):
        tenant = str(tenant_id or "")
        if not tenant or kind not in _KINDS:
            return None
        with self._lock:
            return (self._secrets.get(tenant) or {}).get(kind)

    def set(self, tenant_id, kind, value):
        """Store a key. An empty value removes that kind."""
        tenant = str(tenant_id or "")
        if not tenant or kind not in _KINDS:
            return False
        value = str(value or "").strip()
        with self._lock:
            kinds = self._secrets.setdefault(tenant, {})
            if not value:
                if kind in kinds:
                    del kinds[kind]
                if not kinds:
                    del self._secrets[tenant]
            else:
                if kinds.get(kind) == value:
                    return False
                kinds[kind] = value
            self._save_locked()
            return True

    def remove(self, tenant_id, kind):
        return self.set(tenant_id, kind, "")
