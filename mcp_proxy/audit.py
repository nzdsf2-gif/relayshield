"""Signed, tamper-evident audit trail for the MCP proxy firewall.

Every proxied tools/call is recorded as an append-only log entry with:
  - timestamp, agent, server, tool, argument hash (never raw arguments)
  - the screening verdict and poison category
  - TI enrichment: indicator IDs that fired
  - a hash chain: each entry commits to the previous entry's hash
  - an Ed25519 signature over the entry (when a signing key is set)

Tamper evidence: altering any historical entry breaks the chain,
because each entry's "prev_hash" no longer matches the recomputed
hash of its predecessor. Verification walks the chain and reports the
first broken link.

Storage: in-memory ring (default 10,000 entries) with optional JSONL
file persistence. Deployments needing durable compliance storage
should point MCP_PROXY_AUDIT_FILE at a persistent path.
"""

import hashlib
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_DEFAULT_CAPACITY = 10000


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _entry_hash(entry: dict) -> str:
    """Hash of an entry excluding its own hash and signature fields."""
    core = {k: v for k, v in entry.items()
            if k not in ("entry_hash", "sig", "pubkey")}
    return hashlib.sha256(_canonical(core)).hexdigest()


class AuditTrail:
    """Append-only, hash-chained audit log."""

    def __init__(self, capacity: int = _DEFAULT_CAPACITY,
                 persist_path: str = ""):
        self._capacity = max(100, capacity)
        self._persist_path = persist_path or os.environ.get(
            "MCP_PROXY_AUDIT_FILE", "")
        self._entries = []
        self._lock = threading.Lock()
        self._seq = 0
        # Signer is attached by the proxy so audit entries can carry
        # the same Ed25519 identity as verdicts.
        self.signer = None
        if self._persist_path:
            self._load_persisted()

    # -- persistence ----------------------------------------------------

    def _load_persisted(self):
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._entries.append(entry)
                    self._seq = max(self._seq, entry.get("seq", 0))
            log.info("audit: loaded %d persisted entries from %s",
                     len(self._entries), self._persist_path)
        except OSError:
            pass  # No file yet; start empty.

    def _persist(self, entry: dict):
        if not self._persist_path:
            return
        try:
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            log.error("audit: persist failed: %s", exc)

    # -- recording ------------------------------------------------------

    def record(self, agent_id: str, server_url: str, tool_name: str,
               arguments: dict, decision: str, poison_category: str,
               reasons: list = None, evidence: list = None,
               risk_score: float = 0.0, policy_decision: str = "",
               duration_ms: float = 0.0) -> dict:
        """Append one audit entry. Returns the entry."""
        args_hash = hashlib.sha256(
            _canonical(arguments or {})).hexdigest()
        with self._lock:
            self._seq += 1
            prev_hash = (self._entries[-1]["entry_hash"]
                         if self._entries else "GENESIS")
            entry = {
                "seq": self._seq,
                "ts": time.time(),
                "agent": agent_id,
                "server": server_url,
                "tool": tool_name,
                "args_hash": args_hash,
                "decision": decision,
                "poison_category": poison_category,
                "reasons": reasons or [],
                "evidence": evidence or [],
                "risk_score": round(risk_score, 2),
                "policy_decision": policy_decision,
                "duration_ms": round(duration_ms, 2),
                "prev_hash": prev_hash,
            }
            entry["entry_hash"] = _entry_hash(entry)
            if self.signer is not None and self.signer.signing_enabled:
                from .verdicts import _ed25519_sign, _canonical_bytes
                sig = _ed25519_sign(
                    self.signer._sk, _canonical_bytes(
                        {k: v for k, v in entry.items()
                         if k not in ("sig", "pubkey")}))
                entry["sig"] = sig.hex()
                entry["pubkey"] = self.signer.public_key_hex
            else:
                entry["sig"] = ""
                entry["pubkey"] = ""
            self._entries.append(entry)
            if len(self._entries) > self._capacity:
                # Keep the tail; chain continuity is preserved because
                # each entry still carries its prev_hash.
                del self._entries[:len(self._entries) - self._capacity]
            self._persist(entry)
            return dict(entry)

    # -- reading ---------------------------------------------------------

    def entries(self, limit: int = 100, offset: int = 0) -> list:
        with self._lock:
            window = self._entries[offset:offset + limit]
            return [dict(e) for e in window]

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # -- verification ----------------------------------------------------

    def verify_chain(self) -> dict:
        """Walk the hash chain; report integrity.

        Returns {"ok": True, "checked": N} or
        {"ok": False, "broken_at_seq": S, "checked": N}.
        """
        with self._lock:
            entries = list(self._entries)
        for i, entry in enumerate(entries):
            expected_prev = (entries[i - 1]["entry_hash"]
                             if i > 0 else "GENESIS")
            if entry.get("prev_hash") != expected_prev:
                return {"ok": False, "broken_at_seq": entry.get("seq"),
                        "checked": i}
            if entry.get("entry_hash") != _entry_hash(entry):
                return {"ok": False, "broken_at_seq": entry.get("seq"),
                        "checked": i}
        return {"ok": True, "checked": len(entries)}

    # -- export -----------------------------------------------------------

    def export_json(self, limit: int = 1000) -> list:
        return self.entries(limit=limit)

    def export_csv(self, limit: int = 1000) -> str:
        import csv
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["seq", "ts", "agent", "server", "tool",
                         "decision", "poison_category", "risk_score",
                         "policy_decision", "entry_hash"])
        for e in self.entries(limit=limit):
            writer.writerow([e["seq"], e["ts"], e["agent"], e["server"],
                             e["tool"], e["decision"],
                             e["poison_category"], e["risk_score"],
                             e["policy_decision"], e["entry_hash"]])
        return buf.getvalue()

    def summary(self) -> dict:
        with self._lock:
            n = len(self._entries)
            decisions = {}
            categories = {}
            for e in self._entries:
                decisions[e["decision"]] = decisions.get(
                    e["decision"], 0) + 1
                categories[e["poison_category"]] = categories.get(
                    e["poison_category"], 0) + 1
        chain = self.verify_chain()
        return {
            "entries": n,
            "capacity": self._capacity,
            "decisions": decisions,
            "poison_categories": categories,
            "chain_ok": chain["ok"],
            "persist_path": self._persist_path or None,
        }
