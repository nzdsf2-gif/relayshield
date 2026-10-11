"""OPT-IN verdict telemetry from a proxy deployment back to RelayShield.

OFF BY DEFAULT. With MCP_PROXY_TELEMETRY unset the reporter does not exist: no
thread, no socket, no file. Nothing here can run unless the operator sets
`counts` or `indicators` on purpose.

WHAT IS SENT, and it is the whole list:
  counts      [{category, taxonomy_id, kind, n}]. How many verdicts of each kind.
  indicators  counts, plus [{host, payload_hash, category, taxonomy_id}].
              `host` is the hostname of an UPSTREAM MCP SERVER that served a
              flagged response and only if it is a PUBLIC name or address.
              `payload_hash` is a SHA-256 of that response, never the response.
  always      an anonymous install id (random, generated here, not derived from
              anything), the proxy mode and the taxonomy version.

WHAT IS NEVER SENT: tool arguments, tool names, agent identity, client IPs, raw
payloads, instructions text, audit entries, or any private or internal host.
Argument-level blocks report a COUNT only, because an argument can carry a
customer's own data. The reportable categories are a fixed list of THREAT
categories, so a customer's own policy denials never leave the building.

FAIL-SILENT AND NEVER IN THE REQUEST PATH. record() only increments an in-memory
counter. A background thread flushes on an interval; a failed send is dropped
(counts are trend data, not a ledger) and can never delay or break a verdict.
"""
import hashlib
import ipaddress
import json
import logging
import os
import re
import threading
import urllib.request

from . import taxonomy

log = logging.getLogger(__name__)

# Threat categories only. policy_deny / policy_approval / quarantined_server are
# the operator's own decisions, not threat intelligence, and stay local.
REPORTABLE_CATEGORIES = frozenset({
    "prompt_injection", "pii_leak", "malicious_url", "kit_match", "secret_leak",
    "unknown_synthetic", "oauth_tampering", "credential_exfiltration",
    "attack_chain", "behavioral_anomaly",
})
KINDS = frozenset({"discovery", "result", "call"})
MAX_INDICATORS_PER_REPORT = 50
_INTERNAL_SUFFIXES = (".local", ".internal", ".lan", ".corp", ".home", ".intranet",
                      ".localdomain", ".test", ".example", ".invalid", ".localhost")
_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def public_host(url_or_host: str) -> str:
    """The hostname if it is demonstrably public, else ''. Conservative: anything
    doubtful is treated as private, because a leaked internal hostname is the
    failure this guards against and a missed public one costs one indicator."""
    h = (url_or_host or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0].split("@")[-1]
    if h.startswith("["):
        h = h[1:].split("]", 1)[0]
    else:
        h = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    h = h.rstrip(".")
    if not h:
        return ""
    try:
        ip = ipaddress.ip_address(h)
        return h if ip.is_global else ""
    except ValueError:
        pass
    if "." not in h or len(h) > 253 or h.endswith(_INTERNAL_SUFFIXES) or not _HOST_RE.match(h):
        return ""
    return h


def _load_or_create_install_id(path: str) -> str:
    """Random per-deployment id. Not derived from the host, user or anything else."""
    try:
        with open(path) as f:
            v = f.read().strip()
        if re.fullmatch(r"[0-9a-f]{32}", v):
            return v
    except OSError:
        pass
    v = os.urandom(16).hex()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(v)
    except OSError:
        log.info("telemetry: install id not persisted (using one for this process)")
    return v


class Telemetry:
    """In-memory counters + a background flush. Construct via from_config()."""

    def __init__(self, mode: str, url: str, api_key: str = "", interval: float = 3600.0,
                 install_id: str = "", sender=None, start_thread: bool = True):
        self.mode = mode
        self.url = url
        self.api_key = api_key
        self.interval = max(60.0, interval)
        self.install_id = install_id
        self._send = sender or self._post
        self._lock = threading.Lock()
        self._counts = {}
        self._indicators = {}
        self._stop = threading.Event()
        self._thread = None
        if mode in ("counts", "indicators") and start_thread:
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="rs-proxy-telemetry")
            self._thread.start()

    @classmethod
    def from_config(cls, cfg):
        mode = cfg.telemetry_mode
        if mode == "off":
            return cls("off", "")
        if mode == "indicators" and not cfg.rs_api_key:
            # The indicator tier needs an accountable account. Degrade to counts
            # rather than to silence, and say so once.
            log.warning("telemetry: MCP_PROXY_TELEMETRY=indicators needs "
                        "RELAYSHIELD_API_KEY; reporting counts only")
            mode = "counts"
        return cls(mode, cfg.telemetry_url, cfg.rs_api_key, cfg.telemetry_interval,
                   _load_or_create_install_id(cfg.telemetry_id_file))

    @property
    def enabled(self) -> bool:
        return self.mode in ("counts", "indicators")

    def record(self, category: str, kind: str, taxonomy_ids=(), upstream_url: str = "",
               payload=None):
        """Count one flagged or blocked verdict. Never raises, never blocks."""
        try:
            if not self.enabled or category not in REPORTABLE_CATEGORIES or kind not in KINDS:
                return
            ids = [i for i in (taxonomy_ids or []) if i in taxonomy.ENTRIES] or [""]
            with self._lock:
                for tid in ids:
                    k = (category, tid, kind)
                    self._counts[k] = self._counts.get(k, 0) + 1
                if (self.mode == "indicators" and kind in ("discovery", "result")
                        and payload is not None
                        and len(self._indicators) < MAX_INDICATORS_PER_REPORT):
                    host = public_host(upstream_url)
                    if host:
                        h = hashlib.sha256(json.dumps(
                            payload, sort_keys=True, separators=(",", ":"),
                            default=str).encode()).hexdigest()
                        for tid in ids:
                            self._indicators[(host, h, category, tid)] = True
        except Exception as exc:  # telemetry must never touch a verdict
            log.debug("telemetry record failed: %s", exc)

    def snapshot_and_reset(self) -> dict:
        with self._lock:
            counts, inds = self._counts, self._indicators
            self._counts, self._indicators = {}, {}
        report = {
            "install_id": self.install_id,
            "mode": self.mode,
            "taxonomy_version": taxonomy.TAXONOMY_VERSION,
            "counts": [{"category": c, "taxonomy_id": t, "kind": k, "n": n}
                       for (c, t, k), n in sorted(counts.items())],
        }
        if self.mode == "indicators":
            report["indicators"] = [
                {"host": h, "payload_hash": p, "category": c, "taxonomy_id": t}
                for (h, p, c, t) in sorted(inds)]
        return report

    def flush(self) -> bool:
        """Send what has accumulated. True if something was sent successfully."""
        if not self.enabled:
            return False
        report = self.snapshot_and_reset()
        if not report["counts"] and not report.get("indicators"):
            return False
        try:
            self._send(report)
            return True
        except Exception as exc:
            log.debug("telemetry send failed (dropped): %s", exc)
            return False

    def _post(self, report: dict):
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.mode == "indicators":
            headers["X-RS-API-KEY"] = self.api_key
        req = urllib.request.Request(self.url, data=json.dumps(report).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.flush()

    def stop(self):
        self._stop.set()
