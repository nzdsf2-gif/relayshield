#!/usr/bin/env python3
"""Generate a proxied mcporter.json from an existing one.

Reads your mcporter config, and for each HTTP(S) upstream server writes a
new config that points at a local RelayShield proxy instance instead.
Start one proxy per server first (see mcporter-proxy-setup.md), then run:

    python3 proxy_mcporter.py --in ~/.openclaw/workspace/config/mcpporter.json \\
        --out ~/.openclaw/workspace/config/mcporter.proxied.json \\
        --port-base 8090

Then point mcporter at the new file with --config, or replace the original
(keep a backup). Stdio servers are copied through unchanged: the HTTP proxy
cannot front a stdio transport, so scan those with the pre-deployment
tool scanner instead.
"""

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True, help="existing mcporter.json")
    ap.add_argument("--out", dest="out", required=True, help="output mcporter.json")
    ap.add_argument("--port-base", type=int, default=8090,
                    help="first proxy port; increments per server")
    args = ap.parse_args()

    try:
        with open(args.inp, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("error reading %s: %s" % (args.inp, e), file=sys.stderr)
        return 1

    servers = cfg.get("mcpServers", {})
    proxied = {}
    port = args.port_base
    for name, srv in servers.items():
        base = srv.get("baseUrl", "")
        if base.startswith("http://") or base.startswith("https://"):
            print("proxying %s -> http://127.0.0.1:%d (upstream %s)"
                  % (name, port, base))
            print("  start: MCP_PROXY_UPSTREAM=%s MCP_PROXY_PORT=%d "
                  "python3 -m mcp_proxy" % (base, port))
            proxied[name] = {"baseUrl": "http://127.0.0.1:%d" % port,
                             "headers": {}}
            port += 1
        else:
            print("keeping %s as-is (stdio transport, cannot proxy over HTTP)"
                  % name)
            proxied[name] = srv

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": proxied}, f, indent=2)
        f.write("\n")
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
