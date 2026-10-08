"""Transparent MCP proxy firewall.

Speaks JSON-RPC 2.0 over HTTP. MCP clients (agents) connect to this
proxy as if it were the MCP server. The proxy forwards requests to
the configured upstream server, screening tools/call invocations
against RelayShield threat intelligence first.

Supported methods: initialize, tools/list, tools/call.
Notifications (no id) are forwarded fire-and-forget.
"""

import json
import logging
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import ProxyConfig
from .neighbor import NeighborRegistry
from .quarantine import QuarantineManager
from .screener import Screener
from .verdicts import VerdictSigner, content_hash_of

log = logging.getLogger(__name__)

# MCP error codes (JSON-RPC 2.0 compatible).
ERR_BLOCKED_BY_POLICY = -32001
ERR_SERVER_QUARANTINED = -32002


def _forward_jsonrpc(upstream_url: str, payload: dict, timeout: float = 30.0) -> dict:
    """Forward a JSON-RPC payload to the upstream server."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        upstream_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _error_response(req_id, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP JSON-RPC traffic."""

    server_version = "RelayShield-MCP-Proxy/0.1.0"

    def log_message(self, fmt, *args):
        # Route through logging instead of stderr.
        log.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        cfg: ProxyConfig = self.server.cfg
        screener: Screener = self.server.screener

        # Admin endpoints (not MCP traffic).
        if self.path.startswith("/_rs/"):
            self._handle_admin(cfg)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(
                _error_response(None, -32700, "Parse error: invalid JSON"), 400
            )
            return

        # Support batch requests minimally: process each in order.
        is_batch = isinstance(payload, list)
        requests = payload if is_batch else [payload]
        responses = []

        for req in requests:
            resp = self._handle_one(req, cfg, screener)
            if resp is not None:  # None = notification, no response
                responses.append(resp)

        if is_batch:
            self._send_json(responses)
        elif responses:
            self._send_json(responses[0])
        else:
            # Notification only: 202 accepted, no body per JSON-RPC.
            self.send_response(202)
            self.end_headers()

    def do_GET(self):
        cfg: ProxyConfig = self.server.cfg
        if self.path == "/_rs/dashboard" or self.path == "/_rs/dashboard/":
            try:
                html_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "dashboard.html")
                with open(html_path, "r", encoding="utf-8") as f:
                    html = f.read().encode("utf-8")
            except OSError:
                self._send_json({"error": "dashboard.html not found"}, 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if self.path == "/_rs/neighbors":
            neighbors = {
                url: rep.to_dict()
                for url, rep in self.server.neighbors.all().items()
            }
            self._send_json({"neighbors": neighbors,
                             "quarantine_events":
                                 self.server.quarantine.events[-20:],
                             "verdict_pubkey":
                                 self.server.signer.public_key_hex,
                             "verdicts_signed":
                                 self.server.signer.signing_enabled})
            return
        if self.path == "/_rs/health":
            self._send_json({"status": "ok", "version":
                             "RelayShield-MCP-Proxy/0.2.5",
                             "verdicts_signed":
                                 self.server.signer.signing_enabled})
            return
        self._send_json({"error": "not found"}, 404)

    def _handle_admin(self, cfg: ProxyConfig):
        """Admin actions: POST /_rs/neighbors/clear {"url": ...}."""
        if self.path == "/_rs/neighbors/clear":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {}
            url = body.get("url", "")
            ok = self.server.quarantine.clear(url)
            self._send_json({"cleared": ok, "url": url})
            return
        self._send_json({"error": "unknown admin endpoint"}, 404)

    def _handle_one(self, req: dict, cfg: ProxyConfig, screener: Screener):
        req_id = req.get("id")
        method = req.get("method", "")
        is_notification = "id" not in req

        # Notifications: forward fire-and-forget, no response.
        if is_notification:
            try:
                _forward_jsonrpc(cfg.upstream_url, req)
            except Exception as exc:
                log.warning("notification forward failed: %s", exc)
            return None

        if method == "tools/call":
            return self._handle_tools_call(req, req_id, cfg, screener)

        # initialize, tools/list, and anything else: pure passthrough.
        start = time.monotonic()
        try:
            upstream_resp = _forward_jsonrpc(cfg.upstream_url, req)
        except Exception as exc:
            log.error("upstream forward failed for %s: %s", method, exc)
            return _error_response(req_id, -32603, "Upstream MCP server error",
                                   {"detail": str(exc)})
        elapsed_ms = (time.monotonic() - start) * 1000
        log.info(json.dumps({
            "event": "proxied",
            "method": method,
            "id": req_id,
            "upstream_ms": round(elapsed_ms, 1),
        }))
        # Ensure the response carries our request id.
        if isinstance(upstream_resp, dict) and "id" not in upstream_resp:
            upstream_resp["id"] = req_id
        return upstream_resp

    def _handle_tools_call(self, req: dict, req_id, cfg: ProxyConfig,
                           screener: Screener):
        params = req.get("params") or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        upstream_url = cfg.upstream_url
        neighbors = self.server.neighbors
        quarantine = self.server.quarantine
        t0 = time.monotonic()

        # Fail-closed: quarantined servers get no traffic at all.
        if quarantine.is_quarantined(upstream_url):
            log.warning(json.dumps({
                "event": "tools_call_blocked_quarantined",
                "tool": tool_name,
                "upstream": upstream_url,
            }))
            return _error_response(
                req_id,
                ERR_SERVER_QUARANTINED,
                "Blocked by RelayShield: upstream MCP server is quarantined "
                "as a suspected poisoned neighbor. Clear the quarantine via "
                "POST /_rs/neighbors/clear.",
                {"tool": tool_name, "upstream": upstream_url},
            )

        verdict = {"verdict": "allow", "level": "unknown",
                   "reasons": ["screening disabled"]}
        screen_ms = 0.0
        if cfg.screening_enabled:
            try:
                s0 = time.monotonic()
                verdict = screener.screen_tool_call(tool_name, arguments)
                screen_ms = (time.monotonic() - s0) * 1000
            except Exception as exc:
                log.error("screener error: %s", exc)
                verdict = {"verdict": "allow", "level": "unknown",
                           "reasons": [f"screener error, allowed: {exc}"]}

        total_ms = (time.monotonic() - t0) * 1000
        log.info(json.dumps({
            "event": "tools_call",
            "tool": tool_name,
            "verdict": verdict.get("verdict"),
            "poison_category": verdict.get("poison_category", "clean"),
            "level": verdict.get("level"),
            "score": verdict.get("score", 0),
            "reasons": verdict.get("reasons", []),
            "screen_ms": round(screen_ms, 1),
            "total_ms": round(total_ms, 1),
            "screening_enabled": cfg.screening_enabled,
        }))

        if verdict.get("verdict") == "block":
            # Phase 2.5: issue a signed verdict tying the block to TI
            # evidence. A copied proxy cannot forge this signature.
            signer = self.server.signer
            evidence = [
                {"type": "ti_signal", "id": f"reason-{i}", "detail": r}
                for i, r in enumerate(verdict.get("reasons", []))
            ]
            poison_category = verdict.get("poison_category", "clean")
            signed = signer.issue(
                decision="block",
                tool_name=tool_name,
                content_hash=content_hash_of(arguments),
                evidence=evidence,
                level=verdict.get("level", ""),
                score=verdict.get("score", 0),
                reasons=verdict.get("reasons", []),
                poison_category=poison_category,
            )
            log.info(json.dumps({
                "event": "tools_call_verdict",
                "poison_category": poison_category,
                "verdict_sig": signed.get("sig", "")[:16] + "..." if signed.get("sig") else "unsigned",
                "signed": bool(signed.get("sig")),
            }))
            return _error_response(
                req_id,
                ERR_BLOCKED_BY_POLICY,
                f"Blocked by RelayShield: tool '{tool_name}' arguments "
                f"flagged at level '{verdict.get('level')}'.",
                {
                    "tool": tool_name,
                    "level": verdict.get("level"),
                    "score": verdict.get("score", 0),
                    "poison_category": poison_category,
                    "reasons": verdict.get("reasons", []),
                    "verdict": signed,
                },
            )

        # Clean: forward to upstream.
        try:
            upstream_resp = _forward_jsonrpc(cfg.upstream_url, req)
        except Exception as exc:
            log.error("upstream tools/call failed: %s", exc)
            return _error_response(req_id, -32603, "Upstream MCP server error",
                                   {"detail": str(exc)})
        if isinstance(upstream_resp, dict) and "id" not in upstream_resp:
            upstream_resp["id"] = req_id

        # Phase 2: screen the tool *result* for poisoned content.
        self._screen_result(upstream_url, tool_name, upstream_resp,
                            cfg, screener, neighbors, quarantine)

        return upstream_resp

    def _screen_result(self, upstream_url: str, tool_name: str,
                       upstream_resp: dict, cfg: ProxyConfig,
                       screener: Screener, neighbors, quarantine):
        """Screen an upstream tool result; flag/quarantine the neighbor."""
        if not cfg.result_screening_enabled:
            return
        try:
            result_verdict = screener.screen_tool_result(upstream_resp)
        except Exception as exc:
            # Fail-open for the proxy itself: log and keep the response.
            log.error("result screener error: %s", exc)
            return
        if result_verdict.get("verdict") != "flagged":
            return
        reasons = result_verdict.get("reasons", [])
        details = result_verdict.get("details", {})
        kit_ids = result_verdict.get("kit_ids", [])

        # Phase 2.5: build TI evidence entries, including kit fingerprints.
        evidence = [
            {"type": "ti_signal", "id": f"result-reason-{i}", "detail": r}
            for i, r in enumerate(reasons)
        ]
        for kit_id in kit_ids:
            entry = {"type": "kit_fingerprint", "id": kit_id,
                     "detail": "scam-kit fingerprint in tool result"}
            evidence.append(entry)
        for ke in details.get("kit_evidence", []):
            evidence.append({
                "type": "kit_match",
                "id": ke.get("kit_id", ""),
                "detail": f"family={ke.get('family')} "
                          f"verdict={ke.get('verdict')}",
            })

        # Issue a signed verdict for the poisoned-neighbor flag.
        signer = self.server.signer
        poison_category = result_verdict.get("poison_category", "clean")
        signed = signer.issue(
            decision="flag",
            tool_name=tool_name,
            content_hash=content_hash_of(upstream_resp),
            evidence=evidence,
            reasons=reasons,
            poison_category=poison_category,
            extra={"upstream": upstream_url, "kit_ids": kit_ids},
        )

        log.warning(json.dumps({
            "event": "poisoned_result_detected",
            "tool": tool_name,
            "upstream": upstream_url,
            "poison_category": poison_category,
            "reasons": reasons,
            "details": details,
            "kit_ids": kit_ids,
            "verdict_signed": bool(signed.get("sig")),
        }))
        neighbors.flag(upstream_url,
                       f"poisoned tool result from '{tool_name}'",
                       [e["detail"] for e in evidence])
        quarantine.evaluate(upstream_url, evidence=evidence)


class ProxyServer(HTTPServer):
    """HTTPServer carrying proxy config, screener, and neighbor state."""

    def __init__(self, cfg: ProxyConfig):
        self.cfg = cfg
        self.screener = Screener(
            api_base=cfg.rs_api_base,
            api_key=cfg.rs_api_key,
            timeout=cfg.screen_timeout,
            block_levels=cfg.block_level_set,
            kit_lookup_enabled=cfg.kit_lookup_enabled,
            pii_screening_enabled=cfg.pii_screening_enabled,
            oauth_screening_enabled=cfg.oauth_screening_enabled,
        )
        # Phase 2: neighbor reputation + quarantine.
        self.neighbors = NeighborRegistry(screener=self.screener)
        self.quarantine = QuarantineManager(
            self.neighbors,
            alert_webhook=cfg.alert_webhook,
            auto_quarantine_after=cfg.quarantine_after,
        )
        # Phase 2.5: signed verdicts. The private key comes only from
        # the environment; it is never logged or stored.
        self.signer = VerdictSigner(cfg.signing_key_hex)
        super().__init__(("0.0.0.0", cfg.listen_port), ProxyHandler)
        # Register (and TI-check) the upstream on startup.
        if cfg.upstream_url:
            self.neighbors.register(cfg.upstream_url)


def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = ProxyConfig()
    problems = cfg.validate()
    if problems:
        for p in problems:
            log.error("config: %s", p)
        raise SystemExit(1)
    server = ProxyServer(cfg)
    log.info("MCP proxy listening on :%d, upstream=%s, screening=%s",
             cfg.listen_port, cfg.upstream_url, cfg.screening_enabled)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
