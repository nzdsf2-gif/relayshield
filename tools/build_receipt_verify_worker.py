#!/usr/bin/env python3
"""Regenerate cloudflare_worker_receipt_verify.js from verify_receipt.html.

The HTML file is the source of truth (it also works as a standalone static
page / local file). This script inlines it into the Worker as a JS template
literal, escaping backticks, ${, and </script> so the bundle is safe.

Run from the repo root:  python3 tools/build_receipt_verify_worker.py
"""
import io
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "verify_receipt.html")
OUT = os.path.join(HERE, "cloudflare_worker_receipt_verify.js")

HEADER = """/**
 * verify.relayshield.net — public rsr1 verdict-receipt verifier.
 *
 * Served by the "relayshield-receipt-verify" worker
 * (wrangler.receipt-verify.toml), route verify.relayshield.net/*.
 *
 * The page is fully static: paste a receipt + public key and the Ed25519
 * signature is checked in the visitor's browser. Nothing pasted is ever
 * sent anywhere. The HTML below is GENERATED from verify_receipt.html --
 * edit that file and re-run tools/build_receipt_verify_worker.py.
 */

const HTML = `"""

FOOTER = """`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return new Response("ok", { headers: { "content-type": "text/plain" } });
    }
    if (url.pathname !== "/") {
      return new Response("Not found", { status: 404 });
    }
    return new Response(HTML, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=300",
      },
    });
  },
};
"""


def main():
    html = io.open(SRC, encoding="utf-8").read()
    esc = html.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    esc = esc.replace("</script>", "<\\/script>")
    io.open(OUT, "w", encoding="utf-8").write(HEADER + esc + FOOTER)
    print("wrote %s (%d bytes) from %s" % (OUT, len(esc), SRC))


if __name__ == "__main__":
    main()
