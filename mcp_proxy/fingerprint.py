"""Device fingerprinting for the MCP Proxy Firewall.

A Firewall-native client-instance fingerprint. The Shopify storefront
snippet cannot be reused here: it reads browser APIs (navigator,
screen, canvas, localStorage) and the proxy screens MCP tool calls,
where there is no browser DOM and no TLS client certificate to read
(the proxy is plain HTTP behind fleet TLS termination).

What a fingerprint is here
---------------------------
A SHA-256 hash of the stable client attributes the proxy can actually
see on a tools/call request, canonicalised as sorted-key JSON:

1. ``_rs_agent_id`` -- an authenticated agent ID stamped on the
   request by the deployment's auth layer (the same injection pattern
   as the pre-existing ``_rs_session_id`` transport field). Strongest
   signal when present: it survives reconnects, IP changes, and
   session rotation for the same agent.
2. MCP ``clientInfo`` name + version, captured at ``initialize`` and
   remembered per session key (product strings, e.g. a Claude
   desktop build or an SDK version).
3. ``protocolVersion`` from ``initialize``.
4. The ``User-Agent`` HTTP header.

The client IP is deliberately NOT part of the identity hash: it is
NAT-shared and DHCP-churned, so it would make the fingerprint
unstable and would merge distinct clients behind one NAT. Instead
the IP is hashed separately (different domain separator) and kept
as a ``networks`` signal on the record, so the same instance seen
from a new network is still the same fingerprint, with the network
change visible.

Privacy
-------
No raw PII is stored at rest. The store key is the 64-hex hash only.
Per record it keeps: first/last seen timestamps, call count,
verified tenant IDs seen, hashed network IDs, truncated client
product labels (name/version strings, never credentials), and flag
records (reason, tool, timestamp, tenant). The raw User-Agent string
and the raw client IP are never written to the store or the audit
trail; only their hashes. A deployment salt
(``MCP_PROXY_FINGERPRINT_SALT``) is mixed into every hash so
fingerprints cannot be precomputed across deployments.

Semantics: flag only, except the denylist
----------------------------------------
``check()`` reports whether a fingerprint was previously flagged.
The wiring in ``proxy.py`` adds a flag reason to the call, writes
the fingerprint hash into the audit record, and logs the event. A
flagged fingerprint never blocks, never quarantines, and never feeds
server reputation (a flagged client says nothing about the upstream
server). A fingerprint becomes flagged when an existing screen flags
or blocks one of its calls (TI block, behavior flag, kill-chain
flag), or when an operator flags it via POST /_rs/fingerprints/flag.

The DENYLIST is the one exception: a fingerprint on the denylist
blocks the call outright (standalone blocking). The denylist is
operator-managed config, not learned from observations -- a flag
never denylists a fingerprint on its own, and a single sighting
never does either. Entries are added or removed by an operator via
POST /_rs/fingerprints/denylist/add and .../remove, or by editing
the denylist JSON file (reloaded when its mtime changes). The block
is a clear deny with a reason naming the fingerprint match, and it
is visible in the Audit Trail (decision "block", poison_category
"fingerprint_denylisted", fingerprint hash on the entry).

Persistence
-----------
Same discipline as ``kill_chain_store.py`` and ``audit.py``:
in-memory dict plus append-only JSONL when a path is configured,
load-on-start by replaying event lines, failures logged and never
raised into the request path. One event line per observation is
audit-trail volume; run ``compact()`` (or POST
/_rs/fingerprints/compact) to rewrite the file as one snapshot line
per fingerprint.
"""

import hashlib
import hmac
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

# Truncation for operator-facing client product labels. Labels are
# product strings (client name/version), never credentials, and the
# identity itself is only ever the hash.
_LABEL_MAX = 64

# JSONL event types.
_EVENT_OBSERVE = "observe"
_EVENT_FLAG = "flag"
_EVENT_UNFLAG = "unflag"
_EVENT_SNAPSHOT = "snapshot"

# Denylist (standalone blocking) -----------------------------------------
# A fingerprint on the denylist blocks the call outright. The denylist
# is operator-managed config, NOT learned from observations: a flag
# never denylists a fingerprint on its own, and a single sighting
# never does either. Entries are added/removed by an operator via the
# admin endpoints (or by editing the JSON file, which the store
# reloads when its mtime changes). File format:
#   {"version": 1, "fingerprints": [
#       {"fingerprint": "<64-hex>", "reason": "...",
#        "added_by": "...", "added_ts": 1234567890}]}
# A missing file, an empty list, or an unreadable file means an empty
# denylist: it never blocks. Invalid entries are skipped with a log
# warning, never fatal. The denylist file is separate from the
# observations JSONL on purpose: the JSONL is event-sourced telemetry,
# the denylist is operator config. Fingerprints in the denylist are
# the SAME salted hashes the store computes, so changing
# MCP_PROXY_FINGERPRINT_SALT re-keys every fingerprint and the
# denylist stops matching until entries are re-added under the new
# salt (same as flags).
_DENYLIST_VERSION = 1


def _is_valid_fingerprint(fp: str) -> bool:
    """A fingerprint is a 64-char lowercase hex hash."""
    fp = (fp or "").strip().lower()
    return len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)


def _load_denylist_file(path: str):
    """Read the denylist JSON file. Returns (entries dict, mtime).

    ``entries`` maps fingerprint -> entry dict. Never raises: a
    missing file means an empty denylist; an unreadable or
    malformed file logs and means an empty denylist. Returns mtime
    None when the file is absent.
    """
    if not path:
        return {}, None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.error("fingerprint denylist: unreadable file %s: %s", path, exc)
        return {}, mtime
    items = data.get("fingerprints") if isinstance(data, dict) else None
    if not isinstance(items, list):
        log.error("fingerprint denylist: %s has no 'fingerprints' list",
                  path)
        return {}, mtime
    entries = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        fp = str(item.get("fingerprint") or "").strip().lower()
        if not _is_valid_fingerprint(fp):
            log.warning("fingerprint denylist: skipping invalid entry "
                        "in %s: %r", path, item)
            continue
        entries[fp] = {
            "fingerprint": fp,
            "reason": str(item.get("reason") or "operator denylist"),
            "added_by": str(item.get("added_by") or ""),
            "added_ts": float(item.get("added_ts") or 0),
        }
    return entries, mtime


def _save_denylist_file(path: str, entries: dict) -> bool:
    """Atomically write the denylist JSON file. Returns success."""
    if not path:
        return False
    try:
        payload = {
            "version": _DENYLIST_VERSION,
            "fingerprints": [entries[fp] for fp in sorted(entries)],
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.error("fingerprint denylist: write to %s failed: %s",
                  path, exc)
        return False


def denylist_token_ok(provided: str, expected: str) -> bool:
    """Constant-time check of the denylist operator token.

    The proxy has no role system, so denylist mutations (add/remove/
    reload) are gated on this shared operator bearer token instead.
    The console holds the token and only calls the proxy with it
    after checking the signed-in user's role (Admin or higher); a
    RelayShield operator may also use it directly. An empty expected
    token means the token was never configured, and the check FAILS
    CLOSED: mutations are rejected rather than silently open. Reads
    (GET /_rs/fingerprints/denylist, GET /_rs/fingerprints) are not
    gated; only mutations are.
    """
    expected = (expected or "").strip()
    provided = (provided or "").strip()
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _canonical(obj) -> str:
    """Deterministic JSON for hashing: sorted keys, tight separators."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _hash_with_salt(salt: str, domain: str, canonical: str) -> str:
    """SHA-256 over salt + domain separator + canonical input."""
    material = (salt or "") + "\n" + domain + "\n" + canonical
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def compute_fingerprint(attributes: dict, salt: str = "") -> str:
    """Hash the stable client attributes into a fingerprint.

    ``attributes`` maps field name to value; empty/blank values are
    dropped before hashing, so a client that stops sending one field
    keeps the same fingerprint for the fields it still sends only if
    the remaining set is identical -- callers should pass the same
    field set every time. Returns "" when no usable attribute is
    present (nothing stable to identify: the caller treats the call
    as unfingerprinted, never as an error).
    """
    cleaned = {k: str(v).strip() for k, v in (attributes or {}).items()
               if v is not None and str(v).strip() != ""}
    if not cleaned:
        return ""
    return _hash_with_salt(salt, "fp", _canonical(cleaned))


def network_hash(client_ip: str, salt: str = "") -> str:
    """Hash a client IP as a network signal (never the identity)."""
    ip = str(client_ip or "").strip()
    if not ip:
        return ""
    return _hash_with_salt(salt, "net", ip)


def extract_attributes(req: dict, headers, client_info: dict = None) -> dict:
    """Pull the fingerprint attributes out of one JSON-RPC request.

    ``req`` is the tools/call (or initialize) payload, ``headers`` the
    HTTP headers (``.get("User-Agent")``), ``client_info`` the
    remembered ``{name, version, protocol_version}`` captured at
    initialize for this session (may be empty for clients that never
    sent initialize through this proxy).
    """
    params = req.get("params") or {}
    info = client_info or {}
    # initialize params carry clientInfo inline; prefer the live
    # values when this request IS the initialize.
    live_info = params.get("clientInfo") or {}
    name = (live_info.get("name") or info.get("name") or "").strip()
    version = (live_info.get("version") or info.get("version") or "").strip()
    protocol = (params.get("protocolVersion")
                or info.get("protocol_version") or "").strip()
    attrs = {
        "agent_id": str(req.get("_rs_agent_id") or "").strip(),
        "client_name": name,
        "client_version": version,
        "protocol_version": protocol,
        "user_agent": "",
    }
    try:
        attrs["user_agent"] = (headers.get("User-Agent") or "").strip()
    except Exception:
        attrs["user_agent"] = ""
    return attrs


def fingerprint_for_request(req: dict, headers, client_ip: str,
                            client_info: dict = None,
                            salt: str = "") -> dict:
    """Compute the fingerprint (and network hash) for one request.

    Returns {"fingerprint", "network", "attributes", "label"}.
    ``label`` is the truncated client product label for operator
    display; it is not an identifier and never carries credentials.
    """
    attrs = extract_attributes(req, headers, client_info)
    fp = compute_fingerprint(attrs, salt=salt)
    net = network_hash(client_ip, salt=salt)
    name = attrs.get("client_name") or ""
    version = attrs.get("client_version") or ""
    # Label comes ONLY from clientInfo (product strings the client
    # declares in the MCP handshake). It never falls back to the raw
    # User-Agent header: the UA feeds the hash but is never stored.
    label = (f"{name} {version}".strip())[:_LABEL_MAX]
    return {
        "fingerprint": fp,
        "network": net,
        "attributes": attrs,
        "label": label,
    }


def _new_record(fp: str, ts: float) -> dict:
    return {
        "fingerprint": fp,
        "first_seen": ts,
        "last_seen": ts,
        "call_count": 0,
        "tenants": [],
        "networks": [],
        "client_labels": [],
        "flags": [],
        "status": "clean",
    }


def _apply_event(record: dict, event: dict) -> dict:
    """Fold one persisted event line into a record (load replay)."""
    kind = event.get("type")
    ts = float(event.get("ts") or 0)
    if kind == _EVENT_SNAPSHOT:
        snap = event.get("record") or {}
        if isinstance(snap, dict) and snap.get("fingerprint"):
            return snap
        return record
    if record is None:
        record = _new_record(event.get("fingerprint", ""), ts)
    if kind == _EVENT_OBSERVE:
        record["last_seen"] = max(record.get("last_seen", ts), ts)
        record["call_count"] = int(record.get("call_count", 0)) + 1
        tenant = (event.get("tenant_id") or "").strip()
        if tenant and tenant not in record["tenants"]:
            record["tenants"].append(tenant)
        net = (event.get("network") or "").strip()
        if net and net not in record["networks"]:
            record["networks"].append(net)
        label = (event.get("label") or "").strip()
        if label and label not in record["client_labels"]:
            record["client_labels"].append(label)
    elif kind == _EVENT_FLAG:
        record["status"] = "flagged"
        record["flags"].append({
            "ts": ts,
            "reason": event.get("reason") or "",
            "tool": event.get("tool") or "",
            "tenant_id": event.get("tenant_id") or "",
        })
    elif kind == _EVENT_UNFLAG:
        record["status"] = "clean"
        record["flags"].append({
            "ts": ts,
            "reason": "unflagged: " + (event.get("reason") or ""),
            "tool": "",
            "tenant_id": event.get("tenant_id") or "",
        })
    return record


class FingerprintStore:
    """Flag-only store of hashed per-client-instance fingerprints,
    plus an operator-managed denylist for standalone blocking.

    Mirrors the kill-chain store discipline: in-memory state plus
    append-only JSONL, load-on-start, failures logged never raised.
    Thread-safe; every public method is safe to call from the
    request path. The denylist is a separate JSON config file (see
    ``_load_denylist_file``): a fingerprint on it blocks the call
    outright, while a flagged fingerprint only ever adds a reason.
    """

    def __init__(self, path: str = "", salt: str = "", enabled: bool = True,
                 denylist_path: str = ""):
        self.persist_path = path or ""
        self.salt = salt or ""
        self.enabled = bool(enabled)
        self.denylist_path = denylist_path or ""
        self._lock = threading.Lock()
        self._records = {}
        self._denylist = {}
        self._denylist_mtime = None
        if self.persist_path:
            self._load()
        if self.denylist_path:
            entries, mtime = _load_denylist_file(self.denylist_path)
            self._denylist = entries
            self._denylist_mtime = mtime

    # -- persistence -----------------------------------------------------

    def _load(self):
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    fp = event.get("fingerprint") or (event.get("record") or {}).get("fingerprint")
                    if not fp:
                        continue
                    self._records[fp] = _apply_event(
                        self._records.get(fp), event)
        except OSError:
            pass  # No file yet; start empty.
        except Exception as exc:
            log.error("fingerprint store: load failed: %s", exc)

    def _append(self, event: dict):
        if not self.persist_path:
            return
        try:
            with open(self.persist_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except OSError as exc:
            log.error("fingerprint store: persist to %s failed: %s",
                      self.persist_path, exc)

    # -- observation -----------------------------------------------------

    def observe(self, fp: str, tenant_id: str = "", network: str = "",
                label: str = "") -> dict:
        """Record one call from a fingerprint. Returns its record.

        No-op (returns an empty record) when disabled or when ``fp``
        is empty. Never raises.
        """
        if not self.enabled or not fp:
            return {}
        ts = time.time()
        try:
            with self._lock:
                record = self._records.get(fp)
                if record is None:
                    record = _new_record(fp, ts)
                    self._records[fp] = record
                event = {"type": _EVENT_OBSERVE, "fingerprint": fp,
                         "ts": ts, "tenant_id": tenant_id or "",
                         "network": network or "", "label": label or ""}
                record = _apply_event(record, event)
                self._records[fp] = record
                self._append(event)
                return dict(record)
        except Exception as exc:
            log.error("fingerprint store: observe failed: %s", exc)
            return {}

    # -- flagging ----------------------------------------------------------

    def flag(self, fp: str, reason: str, tool_name: str = "",
             tenant_id: str = "") -> dict:
        """Mark a fingerprint flagged. Returns its record ({} if no-op).

        Called when an existing screen flags or blocks one of the
        fingerprint's calls, or by an operator via the admin
        endpoint. Flag-only: this never blocks a call on its own.
        """
        if not self.enabled or not fp:
            return {}
        ts = time.time()
        try:
            with self._lock:
                record = self._records.get(fp)
                if record is None:
                    record = _new_record(fp, ts)
                    self._records[fp] = record
                event = {"type": _EVENT_FLAG, "fingerprint": fp,
                         "ts": ts, "reason": reason or "",
                         "tool": tool_name or "",
                         "tenant_id": tenant_id or ""}
                record = _apply_event(record, event)
                self._records[fp] = record
                self._append(event)
                return dict(record)
        except Exception as exc:
            log.error("fingerprint store: flag failed: %s", exc)
            return {}

    def unflag(self, fp: str, reason: str = "",
               tenant_id: str = "") -> dict:
        """Clear a fingerprint's flagged status. Returns its record."""
        if not self.enabled or not fp:
            return {}
        ts = time.time()
        try:
            with self._lock:
                record = self._records.get(fp)
                if record is None:
                    return {}
                event = {"type": _EVENT_UNFLAG, "fingerprint": fp,
                         "ts": ts, "reason": reason or "",
                         "tenant_id": tenant_id or ""}
                record = _apply_event(record, event)
                self._records[fp] = record
                self._append(event)
                return dict(record)
        except Exception as exc:
            log.error("fingerprint store: unflag failed: %s", exc)
            return {}

    # -- denylist (standalone blocking) ---------------------------------

    def _maybe_reload_denylist_locked(self):
        """Reload the denylist file if its mtime changed. Lock held."""
        if not self.denylist_path:
            return
        try:
            mtime = os.path.getmtime(self.denylist_path)
        except OSError:
            return  # No file: keep the current in-memory set.
        if (self._denylist_mtime is not None
                and mtime == self._denylist_mtime):
            return
        entries, loaded_mtime = _load_denylist_file(self.denylist_path)
        self._denylist = entries
        self._denylist_mtime = loaded_mtime

    def _note_denylist_written_locked(self):
        """Refresh the remembered mtime after we wrote the file."""
        if not self.denylist_path:
            return
        try:
            self._denylist_mtime = os.path.getmtime(self.denylist_path)
        except OSError:
            pass

    def is_denylisted(self, fp: str):
        """Denylist lookup. Returns the entry dict, or None.

        Never raises. An empty/missing denylist never matches.
        Reloads the file first when its mtime changed, so an
        operator edit lands without a restart.
        """
        if not self.enabled or not fp:
            return None
        try:
            with self._lock:
                self._maybe_reload_denylist_locked()
                entry = self._denylist.get(str(fp).strip().lower())
                return dict(entry) if entry else None
        except Exception as exc:
            log.error("fingerprint denylist: lookup failed: %s", exc)
            return None

    def denylist_add(self, fp: str, reason: str = "",
                     added_by: str = "") -> dict:
        """Add a fingerprint to the denylist (operator action).

        Persists to the denylist file so it survives restarts.
        Returns the entry dict, or {} when the fingerprint is
        invalid or the store is disabled. Never raises. A flag
        never calls this: denylisting is a manual/admin action only.
        """
        if not self.enabled:
            return {}
        fp = str(fp or "").strip().lower()
        if not _is_valid_fingerprint(fp):
            return {}
        try:
            with self._lock:
                self._maybe_reload_denylist_locked()
                entry = {
                    "fingerprint": fp,
                    "reason": (reason or "operator denylist").strip(),
                    "added_by": (added_by or "").strip(),
                    "added_ts": time.time(),
                }
                self._denylist[fp] = entry
                if self.denylist_path:
                    _save_denylist_file(self.denylist_path, self._denylist)
                    self._note_denylist_written_locked()
                return dict(entry)
        except Exception as exc:
            log.error("fingerprint denylist: add failed: %s", exc)
            return {}

    def denylist_remove(self, fp: str) -> bool:
        """Remove a fingerprint from the denylist. Returns success."""
        if not self.enabled:
            return False
        fp = str(fp or "").strip().lower()
        if not _is_valid_fingerprint(fp):
            return False
        try:
            with self._lock:
                self._maybe_reload_denylist_locked()
                if fp not in self._denylist:
                    return False
                del self._denylist[fp]
                if self.denylist_path:
                    _save_denylist_file(self.denylist_path, self._denylist)
                    self._note_denylist_written_locked()
                return True
        except Exception as exc:
            log.error("fingerprint denylist: remove failed: %s", exc)
            return False

    def denylist_list(self) -> list:
        """All denylist entries, sorted by fingerprint. Never raises."""
        try:
            with self._lock:
                self._maybe_reload_denylist_locked()
                return [dict(e) for e in sorted(
                    self._denylist.values(),
                    key=lambda x: x["fingerprint"])]
        except Exception as exc:
            log.error("fingerprint denylist: list failed: %s", exc)
            return []

    def denylist_reload(self) -> int:
        """Force a reload of the denylist file. Returns entry count."""
        try:
            with self._lock:
                if not self.denylist_path:
                    return len(self._denylist)
                entries, mtime = _load_denylist_file(self.denylist_path)
                self._denylist = entries
                self._denylist_mtime = mtime
                return len(entries)
        except Exception as exc:
            log.error("fingerprint denylist: reload failed: %s", exc)
            return 0

    # -- reads -------------------------------------------------------------

    def check(self, fp: str) -> dict:
        """Flag-only lookup. Returns {"status", "flags", ...} or {}.

        ``status`` is "flagged", "clean", or "unknown" (never seen).
        Never raises.
        """
        if not self.enabled or not fp:
            return {}
        try:
            with self._lock:
                record = self._records.get(fp)
            if record is None:
                return {"status": "unknown", "flags": [],
                        "first_seen": 0, "last_seen": 0, "call_count": 0}
            return {
                "status": record.get("status", "clean"),
                "flags": [dict(f) for f in record.get("flags", [])],
                "first_seen": record.get("first_seen", 0),
                "last_seen": record.get("last_seen", 0),
                "call_count": int(record.get("call_count", 0)),
            }
        except Exception as exc:
            log.error("fingerprint store: check failed: %s", exc)
            return {}

    def lookup(self, fp: str) -> dict:
        """Full record for one fingerprint, or {} when unknown."""
        if not fp:
            return {}
        try:
            with self._lock:
                record = self._records.get(fp)
            return dict(record) if record else {}
        except Exception as exc:
            log.error("fingerprint store: lookup failed: %s", exc)
            return {}

    def summary(self) -> dict:
        """Operator overview for GET /_rs/fingerprints."""
        try:
            with self._lock:
                records = list(self._records.values())
                denylist = [dict(e) for e in sorted(
                    self._denylist.values(),
                    key=lambda x: x["fingerprint"])]
            flagged = [r for r in records if r.get("status") == "flagged"]
            return {
                "enabled": self.enabled,
                "persist_path": self.persist_path,
                "denylist_path": self.denylist_path,
                "total": len(records),
                "flagged": len(flagged),
                "denylisted": len(denylist),
                "denylist": denylist,
                "flagged_fingerprints": [
                    {
                        "fingerprint": r["fingerprint"],
                        "first_seen": r["first_seen"],
                        "last_seen": r["last_seen"],
                        "call_count": r["call_count"],
                        "tenants": list(r["tenants"]),
                        "flags": list(r["flags"]),
                    }
                    for r in sorted(flagged,
                                    key=lambda x: x["last_seen"],
                                    reverse=True)
                ],
            }
        except Exception as exc:
            log.error("fingerprint store: summary failed: %s", exc)
            return {"enabled": self.enabled, "total": 0, "flagged": 0,
                    "flagged_fingerprints": []}

    def compact(self) -> bool:
        """Rewrite the JSONL as one snapshot line per fingerprint.

        Drops the per-call event history; the snapshots carry the
        full current state, so a reload after compaction replays
        identically. Returns False when there is no persist path.
        """
        if not self.persist_path:
            return False
        try:
            with self._lock:
                records = [dict(r) for r in self._records.values()]
                tmp = self.persist_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for record in records:
                        f.write(json.dumps({
                            "type": _EVENT_SNAPSHOT,
                            "fingerprint": record["fingerprint"],
                            "ts": time.time(),
                            "record": record,
                        }) + "\n")
                os.replace(tmp, self.persist_path)
            return True
        except OSError as exc:
            log.error("fingerprint store: compact failed: %s", exc)
            return False
