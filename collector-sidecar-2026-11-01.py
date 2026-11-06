#!/usr/bin/env python3
"""RelayShield proxy gate collector, sidecar, push, async, zero datapath cost.

Run as a separate process, alongside the proxy, never inside tools/call.
It tails two local files the proxy already writes, batches new records,
and POSTs them to a Worker endpoint. It never blocks the proxy, never
reads the proxy's memory, and never calls a TAP endpoint.

Inputs, both local files, no network read from the proxy:
- Audit JSONL, default /tmp/relayshield-proxy-audit.jsonl, one JSON
  record per line, with seq, tool, decision, policy_decision, and
  entry_hash for deduplication.
- Proxy log, default /tmp/proxy.log, lines containing settle_outcome,
  with verdict, policy_action, system_outcome, reason, binding_id,
  and passport_id, from v8.

Outputs, batched:
- POST <COLLECTOR_URL> (env MCP_PROXY_COLLECTOR_URL, required),
  JSON body {"verdicts": [...]}, header X-RS-Collector-Secret from
  env MCP_PROXY_COLLECTOR_SECRET, required, never printed, never
  logged. The secret is a shared secret, set on the Worker with
  wrangler secret put, not a RelayShield API key, not a passport.
- Batch size: up to 50 records, or every 5 seconds, whichever first.
- Retry: up to 3 attempts, backoff 1s, 2s, 4s, then drop the batch
  with a warning to /tmp/collector.log, and continue. Dropping a
  batch never blocks the proxy, because the proxy never waits for
  the collector.

State: offsets are kept in /tmp/collector-state.json, with the last
audit file offset and the last proxy log offset, so a restart does
not resend old records, and does not skip new ones, except for a
batch dropped after retries, which is logged, not silently skipped.

Usage, Test window only, after the proxy is running with log to
/tmp/proxy.log and audit to /tmp/relayshield-proxy-audit.jsonl:
  MCP_PROXY_COLLECTOR_URL=http://127.0.0.1:8092/api/gate-verdicts \
  MCP_PROXY_COLLECTOR_SECRET=<from read -s, never pasted> \
  python3 collector-sidecar-2026-11-01.py

For a local test, run a mock Worker first, on 8092, that prints
received batches to its own log, then run the collector against it,
then run a proxy tools/call, and check the mock Worker log for the
new verdict. That proves push works before any production Worker
deploy. The mock Worker is not included here, because it is a
one-file test server, not production code; use the test block in
the collector review file for it.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

AUDIT_FILE = Path(os.environ.get("MCP_PROXY_AUDIT_FILE", "/tmp/relayshield-proxy-audit.jsonl"))
PROXY_LOG = Path(os.environ.get("MCP_PROXY_LOG_FILE", "/tmp/proxy.log"))
STATE_FILE = Path("/tmp/collector-state.json")
COLLECTOR_LOG = Path("/tmp/collector.log")
URL = os.environ.get("MCP_PROXY_COLLECTOR_URL", "").strip()
SECRET = os.environ.get("MCP_PROXY_COLLECTOR_SECRET", "").strip()
BATCH_SIZE = 50
BATCH_SECONDS = 5.0


def log_msg(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n"
    with open(COLLECTOR_LOG, "a", encoding="utf-8") as fh:
        fh.write(line)
    print(line, end="")


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"audit_offset": 0, "log_offset": 0, "seen_hashes": []}


def save_state(state):
    state["seen_hashes"] = state.get("seen_hashes", [])[-200:]
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def read_new_lines(path, offset):
    if not path.exists():
        return [], offset
    data = path.read_bytes()
    if len(data) < offset:
        offset = 0
    chunk = data[offset:]
    if not chunk:
        return [], offset
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    return lines, len(data)


def parse_audit_line(line, seen):
    try:
        rec = json.loads(line)
    except Exception:
        return None
    h = rec.get("entry_hash") or f"audit-{rec.get('seq')}"
    if h in seen:
        return None
    # Do not add to seen here. The caller adds it only after a
    # successful post, so a dropped batch is retried on the next
    # collector restart, instead of being lost forever.
    return {
        "source": "audit",
        "entry_hash": h,
        "seq": rec.get("seq"),
        "ts": rec.get("ts"),
        "tool": rec.get("tool"),
        "decision": rec.get("decision"),
        "policy_decision": rec.get("policy_decision"),
        "poison_category": rec.get("poison_category"),
        "risk_score": rec.get("risk_score"),
        "duration_ms": rec.get("duration_ms"),
        "tenant_id": rec.get("tenant_id"),
        "binding_id": rec.get("binding_id"),
        "location_id": rec.get("location_id"),
    }


def parse_log_line(line, seen):
    if "settle_outcome" not in line:
        return None
    try:
        payload = json.loads(line[line.index("{"):])
    except Exception:
        return None
    key = f"settle-{payload.get('tool')}-{payload.get('reason')}-{payload.get('binding_id')}"
    if key in seen and payload.get("system_outcome") in ("not_completed", "quarantined"):
        # Settle outcomes are rare, and a repeat with the same key in
        # the same run is likely a duplicate log line, not a new verdict.
        # The audit record, with its seq and entry_hash, is the
        # authoritative count, settle is the verdict detail.
        pass
    return {
        "source": "settle",
        "tool": payload.get("tool"),
        "verdict": payload.get("verdict"),
        "policy_action": payload.get("policy_action"),
        "system_outcome": payload.get("system_outcome"),
        "reason": payload.get("reason"),
        "binding_id": payload.get("binding_id"),
        "passport_id": payload.get("passport_id"),
        "tenant_id": payload.get("tenant_id"),
    }


def _tenant_secrets_file():
    return os.environ.get(
        "MCP_PROXY_TENANT_SECRETS_FILE",
        os.path.expanduser("~/.relayshield/tenant-secrets.json"),
    )


def _tenant_collector_secret(tenant_id):
    """Per-tenant collector secret from the proxy's mirrored store.

    Returns None when the tenant has no stored secret, so the caller
    falls back to the global SECRET (current behavior) rather than
    dropping the batch. The Worker does not yet enforce a per-tenant
    collector key; until it does, the fallback keeps verdicts flowing.
    """
    if not tenant_id:
        return None
    try:
        with open(_tenant_secrets_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    entry = (data or {}).get(tenant_id) or {}
    return entry.get("collector_secret") or None


def post_batch(batch, secret=None):
    if secret is None:
        groups = {}
        for rec in batch:
            groups.setdefault((rec or {}).get("tenant_id") or "", []).append(rec)
        ok = True
        for tenant_id, chunk in groups.items():
            tenant_secret = _tenant_collector_secret(tenant_id) or SECRET
            if not post_batch(chunk, secret=tenant_secret):
                ok = False
        return ok

    body = json.dumps({"verdicts": batch}).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={
            "Content-Type": "application/json",
            "X-RS-Collector-Secret": secret or SECRET,
            # Cloudflare returns error 1010 for the default
            # Python-urllib User-Agent, before the Worker ever sees
            # the request. A named collector User-Agent passes, and
            # identifies the client honestly as the collector.
            "User-Agent": "RelayShield-Collector/1.0",
        },
        method="POST",
    )
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            return True
        except Exception as exc:
            log_msg(f"collector post attempt {attempt} failed: {exc}")
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
    return False


def main():
    if not URL or not SECRET:
        print("ABORT: MCP_PROXY_COLLECTOR_URL and MCP_PROXY_COLLECTOR_SECRET are both required.")
        return 1
    state = load_state()
    seen = set(state.get("seen_hashes", []))
    log_msg("collector started, audit=%s log=%s url=%s" % (AUDIT_FILE, PROXY_LOG, URL))
    while True:
        batch = []
        old_audit_offset = state["audit_offset"]
        old_log_offset = state["log_offset"]
        audit_lines, new_audit_offset = read_new_lines(AUDIT_FILE, state["audit_offset"])
        for line in audit_lines:
            rec = parse_audit_line(line, seen)
            if rec:
                batch.append(rec)
        log_lines, new_log_offset = read_new_lines(PROXY_LOG, state["log_offset"])
        for line in log_lines:
            rec = parse_log_line(line, seen)
            if rec:
                batch.append(rec)
        if batch:
            all_ok = True
            for i in range(0, len(batch), BATCH_SIZE):
                chunk = batch[i:i + BATCH_SIZE]
                ok = post_batch(chunk)
                log_msg(f"collector posted {len(chunk)} verdicts, ok={ok}")
                if ok:
                    for rec in chunk:
                        if rec.get("entry_hash"):
                            seen.add(rec["entry_hash"])
                else:
                    all_ok = False
                    log_msg("collector will retry batch on next loop, proxy unaffected")
            if all_ok:
                state["audit_offset"] = new_audit_offset
                state["log_offset"] = new_log_offset
            else:
                state["audit_offset"] = old_audit_offset
                state["log_offset"] = old_log_offset
        else:
            state["audit_offset"] = new_audit_offset
            state["log_offset"] = new_log_offset
        state["seen_hashes"] = list(seen)
        save_state(state)
        time.sleep(BATCH_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
