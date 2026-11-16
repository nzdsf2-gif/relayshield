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
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import ProxyConfig
from .schema_validator import SchemaStore, validate_arguments
from .discovery import DISCOVERY_METHODS, screen_discovery, taxonomy_evidence
from .taxonomy import TAXONOMY_VERSION
from .audit import AuditTrail
from .behavior import BehaviorTracker
from .neighbor import NeighborRegistry
from .policy import PolicyEngine
from .quarantine import QuarantineManager
from .reputation import ReputationStore
from .kill_chain_store import ChainHistoryStore, PivotRegistry
from .screener import Screener, extract_indicators
from .sequence_scoring import (KillChainScorer, SequenceScoringConfig,
                               _external_endpoints, make_session_key)
from .telemetry import Telemetry
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
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
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


def resolve_correlation_identity(req: dict, client_ip: str,
                                 upstream_url: str) -> dict:
    """Resolve the correlation identity for kill-chain scoring.

    One resolution point for the whole package (Phase 5 decision,
    2026-10-23). Fallback order:

    1. Authenticated agent ID: when the deployment's auth layer has
       authenticated the agent, it stamps the request with
       ``_rs_agent_id`` (the same injection pattern as the
       pre-existing ``_rs_session_id`` transport field). The agent
       ID alone is the correlation key, so a chain correlates
       across connections, transport sessions, and time slices for
       that agent.
    2. Transport session ID (``_rs_session_id``): the session key is
       the transport session, as in v1.
    3. Client IP + upstream: the v1 default pairing.

    Returns {"identity", "identity_source", "session_id",
    "session_key"}. The scorer is keyed by session_key; history and
    pivots are recorded under identity.
    """
    agent_id = str(req.get("_rs_agent_id") or "").strip()
    session_id = str(req.get("_rs_session_id") or "").strip()
    if agent_id:
        return {
            "identity": agent_id,
            "identity_source": "agent_id",
            "session_id": session_id,
            "session_key": f"agent:{agent_id}",
        }
    if session_id:
        return {
            "identity": session_id,
            "identity_source": "session_id",
            "session_id": session_id,
            "session_key": make_session_key(
                client_ip, upstream_url, session_id=session_id),
        }
    return {
        "identity": client_ip,
        "identity_source": "ip_upstream",
        "session_id": "",
        "session_key": make_session_key(client_ip, upstream_url),
    }


def _kill_chain_state_dir(cfg: ProxyConfig) -> str:
    """Directory for the kill-chain history/pivot JSONL stores.

    The configured audit directory when audit persistence is set
    (beside MCP_PROXY_AUDIT_FILE); otherwise the proxy state
    directory that holds the telemetry install ID (~/.relayshield).
    """
    if cfg.audit_file:
        return os.path.dirname(os.path.abspath(cfg.audit_file))
    return os.path.dirname(os.path.abspath(cfg.telemetry_id_file))


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
        # Demo scenario runner
        if self.path == "/_rs/demo/run":
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                scenario_id = data.get('scenario', 0)
                
                # Define scenarios with detailed verdicts
                scenarios = {
                    1: {"name": "Clean traffic", "tool": "search_docs",
                        "args": {"query": "refund policy"},
                        "verdict": "ALLOW", "category": "clean",
                        "cause_codes": ["NO_INDICATORS"],
                        "detail": "No screenable indicators in tool arguments"},
                    2: {"name": "Prompt injection", "tool": "fetch_page",
                        "args": {"url": "https://docs.internal/help"},
                        "verdict": "BLOCK", "category": "ssrf_internal_url",
                        "cause_codes": ["SSRF_INTERNAL", "PROTOCOL_PIVOT"],
                        "detail": "Tool argument URL targets internal infrastructure"},
                    3: {"name": "Kit fingerprint", "tool": "render_widget",
                        "args": {"widget": "checkout"},
                        "verdict": "BLOCK", "category": "kit_match",
                        "cause_codes": ["KIT_FINGERPRINT_MATCH"],
                        "detail": "Response matches known phishing kit fingerprint"},
                    4: {"name": "PII leak", "tool": "get_customer",
                        "args": {"customer_id": "42"},
                        "verdict": "FLAG", "category": "pii_leak",
                        "cause_codes": ["PII_SSN_DETECTED"],
                        "detail": "Unredacted SSN pattern in tool response"},
                    7: {"name": "OAuth tampering", "tool": "start_oauth",
                        "args": {"auth_url": "https://evil-auth.example.net/o/oauth2/auth?client_id=demo123"},
                        "verdict": "BLOCK", "category": "oauth_tampering",
                        "cause_codes": ["OAUTH_TAMPERING", "DOMAIN_MISMATCH"],
                        "detail": "OAuth path mimics Google on foreign domain"},
                    8: {"name": "Credential exfiltration", "tool": "get_session",
                        "args": {"session": "current"},
                        "verdict": "FLAG", "category": "credential_exfiltration",
                        "cause_codes": ["JWT_EXFILTRATION"],
                        "detail": "JWT bound for non-IdP domain"},
                    15: {"name": "SSRF redirect chain", "tool": "fetch_page",
                         "args": {"url": "https://bit.ly/docs-help"},
                         "verdict": "BLOCK", "category": "ssrf_redirect_chain",
                         "cause_codes": ["SSRF_REDIRECT_TO_INTERNAL"],
                         "detail": "Redirect chain leads to internal infrastructure"},
                    16: {"name": "DNS rebinding", "tool": "fetch_page",
                         "args": {"url": "https://rebind.example.com/data"},
                         "verdict": "BLOCK", "category": "dns_rebinding",
                         "cause_codes": ["DNS_REBINDING_DETECTED"],
                         "detail": "DNS resolved to external then internal IP"},
                    17: {"name": "Deep document $ref", "tool": "fetch_page",
                         "args": {"url": "https://api.example.com/openapi.json"},
                         "verdict": "BLOCK", "category": "embedded_url_ssrf",
                         "cause_codes": ["EMBEDDED_URL_SSRF"],
                         "detail": "OpenAPI $ref points to internal host"},
                }
                
                scn = scenarios.get(scenario_id, {"name": "Unknown", "tool": "unknown", "args": {}, "expect": "unknown"})
                
                # Run the screening (simplified - uses the proxy's screener)
                # For now, return the scenario definition
                # Full integration would call the actual screening pipeline
                # Convert cause codes to objects for dashboard
                cause_objs = [
                    {"code": code, "description": code.replace("_", " ").title(), "detail": scn["detail"]}
                    for code in scn["cause_codes"]
                ]
                self._send_json({
                    "scenario": scenario_id,
                    "name": scn["name"],
                    "tool": scn["tool"],
                    "args": scn["args"],
                    "status": "completed",
                    "verdict": scn["verdict"],
                    "poison_category": scn["category"],
                    "cause_codes": cause_objs,
                    "detail": scn["detail"],
                    "evidence": [scn["detail"]],
                    "confidence": 95,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
        # Pre-deployment scanner endpoint
        if self.path == "/_rs/scan":
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode('utf-8')
                data = json.loads(body)
                url = data.get('url', '')
                if not url:
                    self._send_json({"error": "URL required"}, 400)
                    return
                from .tool_scanner import scan_tools, check_poppy_json
                from urllib.parse import urlparse
                import urllib.request
                # Route domain-only URLs to poppy.json checker (PAP)
                parsed = urlparse(url)
                if not parsed.path or parsed.path == "/":
                    domain = parsed.netloc or parsed.path
                    domain = domain.split(":")[0]  # strip port
                    findings = check_poppy_json(domain)
                    self._send_json({
                        "url": url,
                        "tool_count": 0,
                        "findings": findings
                    })
                    return
                # Fetch tools/list for MCP servers
                req_data = json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "tools/list", "params": {}
                }).encode('utf-8')
                req = urllib.request.Request(
                    url, data=req_data,
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                tools = result.get('result', {}).get('tools', [])
                findings = scan_tools(tools, source=url)
                self._send_json({
                    "url": url,
                    "tool_count": len(tools),
                    "findings": findings
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return
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
                print(f"DEBUG: Trying to read {html_path}", flush=True)
                with open(html_path, "r", encoding="utf-8") as f:
                    html = f.read().encode("utf-8")
                print(f"DEBUG: Read {len(html)} bytes", flush=True)
            except Exception as e:
                print(f"DEBUG: Dashboard error: {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                self._send_json({"error": f"dashboard error: {e}"}, 500)
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
                             "RelayShield-MCP-Proxy/0.3.0",
                             "verdicts_signed":
                                 self.server.signer.signing_enabled,
                             "behavior_enabled":
                                 self.server.behavior.enabled})
            return
        if self.path == "/_rs/reputation":
            self._send_json(self.server.reputation.summary())
            return
        if self.path == "/_rs/behavior":
            self._send_json({
                "agents": self.server.behavior.profiles(),
                "enabled": self.server.behavior.enabled,
            })
            return
        if self.path.startswith("/_rs/killchain"):
            # Kill-chain score history: scored sessions per
            # correlation identity over a comparison window
            # (24h | 7d | 30d), with count/max/mean aggregates over
            # session peak scores. Same posture as the other
            # /_rs admin reads: no credential check, operator
            # surface only.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            identity = (qs.get("identity", [""])[0] or "").strip() \
                or None
            window = (qs.get("window", ["24h"])[0] or "24h")
            result = self.server.kill_chain_history.query(
                identity=identity, window=window)
            result["enabled"] = self.server.kill_chain.enabled
            result["history_path"] = \
                self.server.kill_chain_history.persist_path
            self._send_json(result)
            return
        if self.path == "/_rs/tenant-policies":
            self._send_json({
                "tenant_policies": getattr(self.server, "tenant_policies", None) or {},
                "tenant_policy_cache": getattr(self.server, "tenant_policy_cache", None) or {},
                "tenant_policy_errors": getattr(self.server, "tenant_policy_errors", None) or {},
            })
            return
        if self.path == "/_rs/policy":
            self._send_json(self.server.policy.summary())
            return
        if self.path == "/_rs/audit":
            self._send_json(self.server.audit.summary())
            return
        if self.path.startswith("/_rs/audit/export"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            fmt = (qs.get("format", ["json"])[0] or "json").lower()
            limit = int(qs.get("limit", ["1000"])[0] or 1000)
            limit = max(1, min(limit, 10000))
            if fmt == "csv":
                body = self.server.audit.export_csv(
                    limit=limit).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({
                    "entries": self.server.audit.export_json(limit=limit),
                    "chain": self.server.audit.verify_chain(),
                })
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
            if ok:
                # Phase 3: reputation recovery on manual clear.
                self.server.reputation.record_quarantine_cleared(
                    url, "cleared by operator")
            self._send_json({"cleared": ok, "url": url})
            return
        if self.path == "/_rs/policy/reload":
            ok = self.server.policy.reload()
            self._send_json({"reloaded": ok,
                             "summary": self.server.policy.summary()})
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

        if method == "initialize":
            return self._handle_initialize(req, req_id, cfg, screener)

        return self._forward_passthrough(req, req_id, cfg, screener)


    def _forward_passthrough(self, req, req_id, cfg, screener):
        # Extracted verbatim from _handle_one, do not change its behavior here.
        method = req.get("method", "")
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
        # Discovery responses (initialize, tools/list, ...) are screened for the
        # cacheScope / instructions-field attacks. Flag-only: the response is
        # forwarded unchanged either way.
        if method in DISCOVERY_METHODS:
            self._screen_discovery(cfg.upstream_url, method, upstream_resp,
                                   cfg, screener)
        return upstream_resp

    def _handle_initialize(self, req, req_id, cfg, screener):
        corr = resolve_correlation_identity(req, self.client_address[0], cfg.upstream_url)
        session_key = corr["session_key"]
        params = req.get("params") or {}
        meta = params.get("_meta") or req.get("_meta") or {}
        binding = meta.get("binding") if isinstance(meta, dict) else None
        if isinstance(params.get("_meta"), dict):
            params["_meta"].pop("binding", None)
        if isinstance(req.get("_meta"), dict):
            req["_meta"].pop("binding", None)
        store = getattr(self.server, "session_bindings", None)
        if store is None:
            store = {}
            self.server.session_bindings = store
        if binding is None:
            store.pop(session_key, None)
            return self._forward_passthrough(req, req_id, cfg, screener)
        passport_compact = binding.get("passport_compact") or meta.get("passport")
        if not passport_compact:
            return _error_response(req_id, -32000, "Session binding requires a passport", {"reason": "passport_invalid"})
        verdict = self._verify_passport_via_gateway(passport_compact)
        if not verdict.get("valid") or verdict.get("revoked"):
            return _error_response(req_id, -32000, "Session binding passport check failed", {"reason": verdict.get("status", "passport_invalid")})
        passport_doc = verdict.get("passport") or {}
        # Phase 1 tenant session: Gateway-verified tenant fields.
        # Passport document wins. A binding-only tenant_id is stored
        # unverified and must NOT be used for policy resolution.
        _passport_tenant = passport_doc.get("tenant_id") if isinstance(passport_doc, dict) else None
        _binding_tenant = binding.get("tenant_id") if isinstance(binding, dict) else None
        if _passport_tenant and _binding_tenant and _passport_tenant != _binding_tenant:
            return _error_response(req_id, -32000, "Session binding tenant mismatch", {"reason": "passport_invalid"})
        _tenant_verified = bool(_passport_tenant)
        _tenant_id = _passport_tenant or _binding_tenant
        store[session_key] = {
            "binding_id": binding.get("binding_id"),
            "payer": binding.get("payer"),
            "counterparty": binding.get("counterparty"),
            "amount": binding.get("amount"),
            "currency": binding.get("currency"),
            "artifacts": binding.get("artifacts") or [],
            "step_up": binding.get("step_up") or {},
            "passport_id": passport_doc.get("passport_id"),
            "passport_expires_at": passport_doc.get("expires_at"),
            "verified_at": time.time(),
            "tenant_id": _tenant_id,
            "location_id": (passport_doc.get("location_id") if isinstance(passport_doc, dict) else None) or binding.get("location_id"),
            "msp_id": (passport_doc.get("msp_id") if isinstance(passport_doc, dict) else None) or binding.get("msp_id"),
            "distributor_id": (passport_doc.get("distributor_id") if isinstance(passport_doc, dict) else None) or binding.get("distributor_id"),
            "tenant_verified": _tenant_verified,
        }
        return self._forward_passthrough(req, req_id, cfg, screener)

    def _verify_passport_via_gateway(self, passport_compact):
        # POST /v1/passport/check, free, no API key, no TAP authorizer.
        # Fail closed on any non-200, 503, timeout, or network error.
        try:
            body = json.dumps({"compact": passport_compact}).encode("utf-8")
            request = urllib.request.Request(
                "https://api.relayshield.net/v1/passport/check",
                data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, dict):
                return data.get("data", data)
            return {"valid": False, "status": "passport_invalid"}
        except Exception:
            return {"valid": False, "status": "passport_invalid", "revoked": False}

    def _fetch_tenant_policy(self, session):
        """Phase 2: fetch and cache a resolved tenant policy.

        Returns a policy dict, or None if no fetch is configured
        or if no last good policy exists. Never raises on fetch
        failure: the caller keeps last good policy.
        """
        tenant_id = (session or {}).get("tenant_id")
        if not tenant_id:
            return None
        location_id = (session or {}).get("location_id")
        cache_key = f"{tenant_id}:{location_id}" if location_id else tenant_id
        now = time.time()
        cache = getattr(self.server, "tenant_policy_cache", None)
        if cache is None:
            cache = {}
            self.server.tenant_policy_cache = cache
        ttl = getattr(self.server, "tenant_policy_ttl_seconds", None)
        if ttl is None:
            try:
                ttl = int(os.environ.get("MCP_PROXY_TENANT_POLICY_TTL_SECONDS", "60"))
            except ValueError:
                ttl = 60
        entry = cache.get(cache_key)
        if entry and (now - entry.get("fetched_at", 0) < ttl):
            return entry.get("policy") or {}
        policies = getattr(self.server, "tenant_policies", None) or {}
        last_good = policies.get(cache_key)
        try:
            fetcher = getattr(self.server, "tenant_policy_fetcher", None)
            if fetcher is not None:
                fetched = fetcher(tenant_id, location_id)
                if not isinstance(fetched, dict):
                    raise ValueError("tenant policy fetcher did not return a dict")
                policy = fetched
            else:
                base_url = os.environ.get("MCP_PROXY_TENANT_POLICY_URL", "").strip()
                if not base_url or "{tenant_id}" not in base_url:
                    return last_good
                url = base_url.replace("{tenant_id}", tenant_id)
                if location_id:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}location_id={location_id}"
                headers = {"Content-Type": "application/json"}
                api_key = os.environ.get("MCP_PROXY_TENANT_POLICY_KEY", "").strip()
                if api_key:
                    headers["Authorization"] = "Bearer " + api_key
                request = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                if isinstance(data, dict):
                    inner = data.get("data", data)
                    policy = inner.get("policies") if isinstance(inner, dict) else None
                    if not isinstance(policy, dict):
                        policy = inner if isinstance(inner, dict) else {}
                else:
                    policy = {}
        except Exception as exc:
            log.warning("tenant policy fetch failed for %s: %s", cache_key, exc)
            errors = getattr(self.server, "tenant_policy_errors", None)
            if errors is None:
                errors = {}
                self.server.tenant_policy_errors = errors
            errors[cache_key] = str(exc)
            return last_good
        cache[cache_key] = {"policy": policy, "fetched_at": now, "error": None}
        if not hasattr(self.server, "tenant_policies") or self.server.tenant_policies is None:
            self.server.tenant_policies = {}
        self.server.tenant_policies[cache_key] = policy
        return policy

    def _intent_gate(self, session_key, tool_name, arguments, cfg, req=None):
        # Returns None to fall through, or a JSON-RPC error response to block.
        # Policy 1: Bound actions only. Policy 2: Step-up for high-risk actions.
        if _tool_is_read_only(tool_name, arguments):
            return None
        store = getattr(self.server, "session_bindings", None) or {}
        session = store.get(session_key)
        # v4 fix: Policy 1 defaults to Off, not Enforce. A patch that defaults
        # to Enforce blocks every existing agent on day one, and breaks 6
        # existing tests that have no session binding. Off is simply the
        # policy not enabled for that tenant or location. Audit records
        # and flags but does not block. Enforce blocks, only when explicitly enabled.
        # Phase 2 tenant policy resolution. Verified tenant only.
        # _fetch_tenant_policy populates server.tenant_policies from
        # the console, with cache and last-good fallback. Unverified
        # or missing tenant falls back to the global env mode,
        # preserving dedicated per-SMB behavior.
        _session_for_mode = store.get(session_key) or {}
        if _session_for_mode.get("tenant_verified") and _session_for_mode.get("tenant_id"):
            self._fetch_tenant_policy(_session_for_mode)
            _tenant_policies = getattr(self.server, "tenant_policies", None) or {}
            _loc_key = None
            if _session_for_mode.get("location_id"):
                _loc_key = f"{_session_for_mode.get('tenant_id')}:{_session_for_mode.get('location_id')}"
            _tenant_policy = {}
            if _loc_key and isinstance(_tenant_policies.get(_loc_key), dict):
                _tenant_policy = _tenant_policies.get(_loc_key) or {}
            elif isinstance(_tenant_policies.get(_session_for_mode.get("tenant_id")), dict):
                _tenant_policy = _tenant_policies.get(_session_for_mode.get("tenant_id")) or {}
            mode = _tenant_policy.get("policy1_mode", "off")
            if mode not in ("audit", "enforce"):
                mode = "off"
        else:
            mode = getattr(cfg, "intent_binding_mode", "off")
        if mode not in ("audit", "enforce"):
            return None
        if mode == "audit":
            return None
        if session is None:
            return _error_response(0, -32000, "Blocked by RelayShield: state-changing tool requires a session binding", {"reason": "missing_binding", "tool": tool_name})
        # Expiry, from the verified passport document, per call.
        expires_at = session.get("passport_expires_at")
        if expires_at:
            try:
                from datetime import datetime, timezone
                expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= expires:
                    return _error_response(0, -32000, "Blocked by RelayShield: session passport expired", {"reason": "passport_expired", "tool": tool_name})
            except Exception:
                pass
        # Per-call revocation check, small cascade piece, Option B only.
        # Passport status is free, no API key, no TAP authorizer.
        # Cache is 60 seconds, never caching revoked as valid.
        # A known revoked status blocks, a lookup failure logs and
        # falls back to expiry-only, so a status outage does not
        # block every tool call, but a known revocation always does.
        _passport_id = session.get("passport_id")
        if _passport_id:
            _now = time.time()
            _cache = getattr(self.server, "passport_status_cache", None)
            if _cache is None:
                _cache = {}
                self.server.passport_status_cache = _cache
            _cached = _cache.get(_passport_id)
            _status = None
            if _cached and _cached.get("status") == "revoked":
                _status = "revoked"
            elif _cached and (_now - _cached.get("checked_at", 0)) < 60:
                _status = _cached.get("status")
            else:
                try:
                    _url = f"https://api.relayshield.net/v1/passport/{_passport_id}/status"
                    _req = urllib.request.Request(_url, method="GET")
                    with urllib.request.urlopen(_req, timeout=5) as _resp:
                        _data = json.loads(_resp.read().decode("utf-8"))
                    _status = (_data.get("data", _data) or {}).get("status") if isinstance(_data, dict) else None
                    if _status:
                        _cache[_passport_id] = {"status": _status, "checked_at": _now}
                except Exception as _exc:
                    log.warning("passport status lookup failed for %s: %s", _passport_id, _exc)
                    _status = None
            if _status == "revoked":
                return _error_response(0, -32000, "Blocked by RelayShield: session passport revoked", {"reason": "passport_revoked", "tool": tool_name})
            if _status == "expired":
                return _error_response(0, -32000, "Blocked by RelayShield: session passport expired", {"reason": "passport_expired", "tool": tool_name})
        # Intent match, Item 3 mapping, first present field wins.
        mismatch = _intent_mismatch(session, tool_name, arguments)
        if mismatch:
            return _error_response(0, -32000, "Blocked by RelayShield: tool call does not match bound intent", {"reason": mismatch, "tool": tool_name})
        # Policy 2: Step-up, mirroring relayshield_intent_binding.validate_step_up_attestations.
        # step_up.required False: no validation, attestations ignored.
        # Otherwise every method in step_up.satisfied_by must be covered by an attestation.
        # Attestations are read from the call _meta, if present, not from the session store.
        # A block here never consumes the binding, matching _settle_core.
        step_up = session.get("step_up") or {}
        if isinstance(step_up, dict) and step_up.get("required"):
            required = step_up.get("satisfied_by") or []
            attestations = []
            if isinstance(req, dict):
                params_meta = (req.get("params") or {}).get("_meta") or {}
                req_meta = req.get("_meta") or {}
                attestations = params_meta.get("attestations") or req_meta.get("attestations") or []
            covered = set()
            for att in attestations:
                if isinstance(att, dict) and att.get("method"):
                    covered.add(att.get("method"))
            if any(method not in covered for method in required):
                return _error_response(0, -32000, "Blocked by RelayShield: step-up attestation missing", {"reason": "step_up_attestation_missing", "tool": tool_name})
        return None

    def _screen_discovery(self, upstream_url: str, method: str,
                          upstream_resp: dict, cfg: ProxyConfig,
                          screener: Screener):
        """Screen a discovery response; flag the server, never block."""
        # Store tool schemas for argument validation on tools/list
        if method == "tools/list":
            try:
                tools = upstream_resp.get("result", {}).get("tools", [])
                if tools and hasattr(self, 'schema_store'):
                    self.schema_store.update_from_tools_list(tools)
            except Exception:
                pass
        if not cfg.result_screening_enabled:
            return
        try:
            verdict = screen_discovery(method, upstream_resp, screener)
        except Exception as exc:
            log.error("discovery screener error: %s", exc)
            return
        if verdict.get("verdict") != "flagged":
            return
        reasons = verdict["reasons"]
        category = verdict["poison_category"]
        ids = verdict["taxonomy_ids"]
        evidence = [{"type": "ti_signal", "id": f"discovery-reason-{i}", "detail": r}
                    for i, r in enumerate(reasons)]
        # What makes the flag actionable: the matching taxonomy entries, with
        # their mitigations, ride in the evidence of the signed verdict.
        evidence += taxonomy_evidence(ids)
        signed = self.server.signer.issue(
            decision="flag", tool_name=method,
            content_hash=content_hash_of(upstream_resp),
            evidence=evidence, reasons=reasons, poison_category=category,
            extra={"upstream": upstream_url, "taxonomy_ids": ids,
                   "taxonomy_version": TAXONOMY_VERSION},
        )
        log.warning(json.dumps({
            "event": "poisoned_discovery_detected",
            "method": method, "upstream": upstream_url,
            "poison_category": category, "reasons": reasons,
            "taxonomy_ids": ids, "details": verdict["details"],
            "verdict_signed": bool(signed.get("sig")),
        }))
        self.server.neighbors.flag(
            upstream_url, f"poisoned {method} response",
            [e["detail"] for e in evidence])
        self.server.reputation.record_flag(upstream_url, f"{category}: {method}")
        self.server.audit.record(
            self.client_address[0], upstream_url, method, {},
            decision="flag", poison_category=category,
            reasons=reasons, evidence=evidence)
        self.server.telemetry.record(category, "discovery", ids, upstream_url,
                                     upstream_resp)
        if self.server.quarantine.evaluate(upstream_url, evidence=evidence):
            self.server.reputation.record_quarantine(
                upstream_url, "auto-quarantine: poisoned discovery response")

    def _record_kill_chain_outcome(self, corr: dict, upstream_url: str,
                                   tool_name: str, seq_result: dict,
                                   indicators: dict = None,
                                   source: str = "call"):
        """Persist a scored chain: history record + pivot registration.

        Called for every non-allow sequence verdict (flag or block)
        from either hook. History is recorded unconditionally (it is
        the /_rs/killchain data source); a pivot is registered only
        when the chain actually observed external endpoints or
        indicators worth pivoting on. Failures are logged, never
        raised into the request path.
        """
        verdict = seq_result.get("verdict")
        if verdict not in ("flag", "block"):
            return
        seq_detail = seq_result.get("sequence", {})
        try:
            self.server.kill_chain_history.record(
                identity=corr["identity"],
                identity_source=corr["identity_source"],
                session_key=corr["session_key"],
                session_id=corr["session_id"],
                server=upstream_url,
                tool=tool_name,
                score=seq_result.get("risk_score", 0.0),
                stages=seq_detail.get("stages_seen", []),
                decision=verdict,
                chain=seq_detail.get("chain", 1),
                source=source,
            )
        except Exception as exc:
            log.error("kill-chain history record error: %s", exc)
        indicators = indicators or {}
        hosts = indicators.get("hosts", [])
        if hosts or indicators.get("urls") or indicators.get("domains") \
                or indicators.get("ips"):
            try:
                self.server.kill_chain_pivots.register(
                    identity=corr["identity"],
                    session_key=corr["session_key"],
                    server=upstream_url,
                    tool=tool_name,
                    source=source,
                    indicators=indicators,
                    stages=seq_detail.get("stages_seen", []),
                    score=seq_result.get("risk_score", 0.0),
                )
            except Exception as exc:
                log.error("kill-chain pivot register error: %s", exc)

    def _audit_session_fields(self, session_key):
        """Phase 3a call-site helper: tenant and binding stamps.

        Returns (tenant_id, binding_id, location_id), all strings.
        Tenant and location are stamped only when the session is
        Gateway-verified. Binding is stamped whenever present.
        No session, no tenant, or no binding means empty strings,
        never an error.
        """
        try:
            session = (getattr(self.server, "session_bindings", None) or {}).get(session_key) or {}
        except Exception:
            session = {}
        if not isinstance(session, dict):
            return "", "", ""
        verified = bool(session.get("tenant_verified"))
        tenant_id = session.get("tenant_id") if verified else ""
        location_id = session.get("location_id") if verified else ""
        binding_id = session.get("binding_id") or ""
        return (tenant_id or "", binding_id or "", location_id or "")

    def _handle_tools_call(self, req: dict, req_id, cfg: ProxyConfig,
                           screener: Screener):
        params = req.get("params") or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        upstream_url = cfg.upstream_url
        neighbors = self.server.neighbors
        quarantine = self.server.quarantine
        behavior = self.server.behavior
        reputation = self.server.reputation
        t0 = time.monotonic()

        # Phase 3: agent identity for behavioral baselining. The client
        # IP is the available signal; deployments with authenticated
        # agents should override this with a stable agent ID.
        agent_id = self.client_address[0]
        corr = resolve_correlation_identity(req, agent_id, upstream_url)
        session_key = corr["session_key"]
        _audit_tenant, _audit_binding, _audit_location = self._audit_session_fields(session_key)

        # Fail-closed: quarantined servers get no traffic at all.
        if quarantine.is_quarantined(upstream_url):
            log.warning(json.dumps({
                "event": "tools_call_blocked_quarantined",
                "tool": tool_name,
                "upstream": upstream_url,
            }))
            self.server.audit.record(
                agent_id, upstream_url, tool_name, arguments,
                decision="block", poison_category="quarantined_server",
                reasons=["upstream server is quarantined"],
                policy_decision="",
                tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
            )
            return _error_response(
                req_id,
                ERR_SERVER_QUARANTINED,
                "Blocked by RelayShield: upstream MCP server is quarantined "
                "as a suspected poisoned neighbor. Clear the quarantine via "
                "POST /_rs/neighbors/clear.",
                {"tool": tool_name, "upstream": upstream_url},
            )

        # Phase 4: policy enforcement runs before TI screening. Policy
        # denies are fast and deterministic: no network, no corpus.
        policy = self.server.policy
        policy_result = {"decision": "allow", "reasons": [],
                         "poison_category": "clean"}
        if policy.enabled:
            try:
                policy_result = policy.evaluate(
                    agent_id, tool_name, upstream_url, arguments)
            except Exception as exc:
                log.error("policy engine error: %s", exc)
        if policy_result.get("decision") == "deny":
            signer = self.server.signer
            signed = signer.issue(
                decision="block",
                tool_name=tool_name,
                content_hash=content_hash_of(arguments),
                evidence=[{"type": "policy_rule", "id": "policy-deny",
                           "detail": r}
                          for r in policy_result.get("reasons", [])],
                reasons=policy_result.get("reasons", []),
                poison_category=policy_result.get(
                    "poison_category", "policy_deny"),
            )

        # Schema validation: check arguments against tool's declared JSON Schema.
        # Catches malformed input that weak server-side validation would miss.
        if hasattr(self.server, 'schema_store'):
            schema = self.server.schema_store.get_schema(tool_name)
            if schema:
                is_valid, violations = validate_arguments(tool_name, arguments, schema)
                blocking = [v for v in violations if v["severity"] in ("HIGH", "CRITICAL")]
                if blocking:
                    log.warning(json.dumps({
                        "event": "tools_call_blocked_schema",
                        "tool": tool_name,
                        "violations": blocking,
                    }))
                    return _error_response(
                        req_id, -32602,
                        f"Blocked by RelayShield: argument validation failed: {blocking[0]['message']}",
                        {"tool": tool_name, "violations": blocking},
                    )
            # Policy deny: audit the block and return the signed
            # verdict issued above. This tail is gated on the deny
            # decision: `signed` exists only on that path.
            if policy_result.get("decision") == "deny":
                log.warning(json.dumps({
                    "event": "tools_call_blocked_policy",
                    "tool": tool_name,
                    "agent": agent_id,
                    "reasons": policy_result.get("reasons", []),
                }))
                self.server.audit.record(
                    agent_id, upstream_url, tool_name, arguments,
                    decision="block",
                    poison_category=policy_result.get(
                        "poison_category", "policy_deny"),
                    reasons=policy_result.get("reasons", []),
                    evidence=signed.get("evidence", []),
                    policy_decision="deny",
                    tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
                )
                return _error_response(
                    req_id,
                    ERR_BLOCKED_BY_POLICY,
                    f"Blocked by RelayShield policy: "
                    f"{'; '.join(policy_result.get('reasons', []))}",
                    {
                        "tool": tool_name,
                        "poison_category": policy_result.get(
                            "poison_category", "policy_deny"),
                        "reasons": policy_result.get("reasons", []),
                        "verdict": signed,
                    },
                )
        policy_decision = policy_result.get("decision", "allow")

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

        # Phase 3: behavioral screening runs on every call, even when
        # TI screening is disabled. It never blocks on its own; it
        # flags, scores risk, and feeds the reputation graph.
        behavior_result = {"verdict": "allow", "poison_category": "clean",
                           "reasons": [], "risk_score": 0.0}
        if behavior.enabled:
            try:
                behavior_result = behavior.check(
                    agent_id, tool_name, arguments,
                    server_url=upstream_url)
            except Exception as exc:
                log.error("behavior tracker error: %s", exc)

        # Phase 5: kill-chain sequence scoring runs on every call,
        # even when TI screening is disabled. It scores the session's
        # stage progression (recon -> access -> staging -> exfil),
        # not the call in isolation. Correlation identity resolves
        # in one place (resolve_correlation_identity): an
        # authenticated agent ID when the deployment stamps one,
        # else the transport session ID, else the (agent IP,
        # upstream) pair as in behavior.py.
        # corr and session_key moved above, after agent_id, before first audit call (Phase 3a call-site step 2v3)
        _gate = self._intent_gate(session_key, tool_name, arguments, cfg, req=req)
        if _gate is not None:
            _gate["id"] = req_id
            # Phase 1 gate stamp: tenant and binding, when a session exists.
            # AuditTrail stamping is Phase 3; this does not change it.
            try:
                _gate_session = (getattr(self.server, "session_bindings", None) or {}).get(session_key) or {}
                if isinstance(_gate, dict) and isinstance(_gate.get("error"), dict):
                    _gate_data = _gate["error"].get("data")
                    if isinstance(_gate_data, dict):
                        if _gate_session.get("tenant_id"):
                            _gate_data["tenant_id"] = _gate_session.get("tenant_id")
                        if _gate_session.get("binding_id"):
                            _gate_data["binding_id"] = _gate_session.get("binding_id")
            except Exception:
                pass
            return _gate
        sequence_result = {"verdict": "allow",
                           "poison_category": "clean",
                           "reasons": [], "risk_score": 0.0}
        if self.server.kill_chain.enabled:
            try:
                sequence_result = self.server.kill_chain.observe_call(
                    session_key, tool_name, arguments,
                    server_url=upstream_url)
                if sequence_result.get("verdict") in ("flag", "block"):
                    indicators = extract_indicators(arguments)
                    indicators["hosts"] = _external_endpoints(arguments)
                    self._record_kill_chain_outcome(
                        corr, upstream_url, tool_name, sequence_result,
                        indicators=indicators, source="call")
            except Exception as exc:
                log.error("kill-chain scorer error: %s", exc)

        total_ms = (time.monotonic() - t0) * 1000
        log.info(json.dumps({
            "event": "tools_call",
            "tool": tool_name,
            "verdict": verdict.get("verdict"),
            "poison_category": verdict.get("poison_category", "clean"),
            "level": verdict.get("level"),
            "score": verdict.get("score", 0),
            "reasons": verdict.get("reasons", []),
            "behavior_verdict": behavior_result.get("verdict"),
            "behavior_category": behavior_result.get("poison_category"),
            "behavior_reasons": behavior_result.get("reasons", []),
            "risk_score": round(behavior_result.get("risk_score", 0.0), 1),
            "kill_chain_verdict": sequence_result.get("verdict"),
            "kill_chain_category": sequence_result.get("poison_category"),
            "kill_chain_reasons": sequence_result.get("reasons", []),
            "sequence_score": round(
                sequence_result.get("risk_score", 0.0), 1),
            "screen_ms": round(screen_ms, 1),
            "total_ms": round(total_ms, 1),
            "screening_enabled": cfg.screening_enabled,
        }))

        # Phase 3: behavioral flags feed server reputation. High risk
        # scores can trigger quarantine evaluation.
        if behavior_result.get("verdict") == "flag":
            bcat = behavior_result.get("poison_category", "clean")
            for reason in behavior_result.get("reasons", []):
                if bcat == "attack_chain":
                    reputation.record_attack_chain(upstream_url, reason)
                else:
                    reputation.record_behavior_anomaly(upstream_url,
                                                       reason)
            risk = behavior_result.get("risk_score", 0.0)
            if risk >= cfg.behavior_quarantine_score:
                log.warning(json.dumps({
                    "event": "behavior_risk_quarantine",
                    "tool": tool_name,
                    "upstream": upstream_url,
                    "risk_score": round(risk, 1),
                    "threshold": cfg.behavior_quarantine_score,
                }))
                neighbors.flag(
                    upstream_url,
                    f"behavioral risk score {risk:.1f} reached "
                    f"quarantine threshold",
                    behavior_result.get("reasons", []))
                if quarantine.evaluate(upstream_url):
                    reputation.record_quarantine(
                        upstream_url,
                        f"behavioral risk {risk:.1f}")
        else:
            reputation.record_clean_call(upstream_url)

        # Phase 5: kill-chain flags feed server reputation as attack
        # chains, like behavioral attack-chain flags do. Kill-chain
        # blocks are handled after TI screening below, so a TI block
        # on the same call keeps its own signed verdict.
        if sequence_result.get("verdict") == "flag":
            for reason in sequence_result.get("reasons", []):
                reputation.record_attack_chain(upstream_url, reason)

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
            # Counts only: an argument can carry the customer's own data.
            self.server.telemetry.record(poison_category, "call")
            # Phase 4: audit the block decision.
            self.server.audit.record(
                agent_id, upstream_url, tool_name, arguments,
                decision="block", poison_category=poison_category,
                reasons=verdict.get("reasons", []),
                evidence=evidence,
                risk_score=behavior_result.get("risk_score", 0.0),
                policy_decision=policy_decision,
                duration_ms=total_ms,
                tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
            )
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

        if sequence_result.get("verdict") == "block":
            # Phase 5: the session completed a kill-chain progression.
            # Block with a signed verdict in the TI block shape, with
            # the chain explanation as the evidence.
            signer = self.server.signer
            seq_detail = sequence_result.get("sequence", {})
            evidence = [{
                "type": "kill_chain",
                "id": f"chain-{seq_detail.get('chain', 1)}",
                "detail": seq_detail.get("explanation", ""),
            }]
            poison_category = sequence_result.get(
                "poison_category", "kill_chain")
            signed = signer.issue(
                decision="block",
                tool_name=tool_name,
                content_hash=content_hash_of(arguments),
                evidence=evidence,
                score=int(sequence_result.get("risk_score", 0.0)),
                reasons=sequence_result.get("reasons", []),
                poison_category=poison_category,
            )
            self.server.telemetry.record(poison_category, "call")
            self.server.audit.record(
                agent_id, upstream_url, tool_name, arguments,
                decision="block", poison_category=poison_category,
                reasons=sequence_result.get("reasons", []),
                evidence=evidence,
                risk_score=sequence_result.get("risk_score", 0.0),
                policy_decision=policy_decision,
                duration_ms=total_ms,
                tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
            )
            # Quarantine coupling (Phase 5 decision, 2026-10-23): a
            # sequence block feeds the quarantine mechanism exactly
            # the way a threat-intel block does in _screen_result:
            # flag the neighbor with the verdict evidence, run
            # quarantine evaluation, and record the quarantine in
            # the reputation graph when the threshold is reached.
            neighbors.flag(
                upstream_url,
                f"kill-chain sequence block on '{tool_name}'",
                [e["detail"] for e in evidence])
            if quarantine.evaluate(upstream_url, evidence=evidence):
                reputation.record_quarantine(
                    upstream_url,
                    "auto-quarantine: kill-chain sequence block")
            return _error_response(
                req_id,
                ERR_BLOCKED_BY_POLICY,
                f"Blocked by RelayShield: tool '{tool_name}' completed "
                f"a kill-chain sequence in this session.",
                {
                    "tool": tool_name,
                    "score": sequence_result.get("risk_score", 0),
                    "poison_category": poison_category,
                    "reasons": sequence_result.get("reasons", []),
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
        # A result-side kill-chain completion at block level holds
        # the response (Phase 5 decision, 2026-10-23): _screen_result
        # returns a hold dict and the caller gets the block error
        # shape with the signed kill-chain verdict instead of the
        # upstream response.
        hold = self._screen_result(upstream_url, tool_name, upstream_resp,
                                   cfg, screener, neighbors, quarantine,
                                   corr=corr)
        if hold is not None:
            kc_result = hold["kc_result"]
            signer = self.server.signer
            poison_category = kc_result.get(
                "poison_category", "kill_chain")
            signed = signer.issue(
                decision="block",
                tool_name=tool_name,
                content_hash=content_hash_of(upstream_resp),
                evidence=hold["evidence"],
                score=int(kc_result.get("risk_score", 0.0)),
                reasons=kc_result.get("reasons", []),
                poison_category=poison_category,
            )
            self.server.telemetry.record(poison_category, "result")
            self.server.audit.record(
                agent_id, upstream_url, tool_name, arguments,
                decision="block", poison_category=poison_category,
                reasons=kc_result.get("reasons", []),
                evidence=hold["evidence"],
                risk_score=kc_result.get("risk_score", 0.0),
                policy_decision=policy_decision,
                duration_ms=(time.monotonic() - t0) * 1000,
                tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
            )
            return _error_response(
                req_id,
                ERR_BLOCKED_BY_POLICY,
                f"Blocked by RelayShield: result of tool '{tool_name}' "
                f"completed a kill-chain sequence in this session; "
                f"the response was held.",
                {
                    "tool": tool_name,
                    "score": kc_result.get("risk_score", 0),
                    "poison_category": poison_category,
                    "reasons": kc_result.get("reasons", []),
                    "verdict": signed,
                    "held_result": True,
                },
            )

        # Phase 4: audit the allowed call.
        self.server.audit.record(
            agent_id, upstream_url, tool_name, arguments,
            decision="allow",
            poison_category=behavior_result.get(
                "poison_category", "clean"),
            reasons=behavior_result.get("reasons", []),
            risk_score=behavior_result.get("risk_score", 0.0),
            policy_decision=policy_decision,
            duration_ms=(time.monotonic() - t0) * 1000,
            tenant_id=_audit_tenant, binding_id=_audit_binding, location_id=_audit_location
        )

        return upstream_resp

    def _screen_result(self, upstream_url: str, tool_name: str,
                       upstream_resp: dict, cfg: ProxyConfig,
                       screener: Screener, neighbors, quarantine,
                       corr: dict = None):
        """Screen an upstream tool result; flag/quarantine the neighbor.

        Returns a hold dict when a result-side kill-chain completion
        reaches block level (the caller then replaces the response
        with the block error); otherwise returns None and the
        response is delivered as before. Sub-block sequence scores
        still flag and deliver.
        """
        if not cfg.result_screening_enabled:
            return None
        try:
            result_verdict = screener.screen_tool_result(upstream_resp)
        except Exception as exc:
            # Fail-open for the proxy itself: log and keep the response.
            log.error("result screener error: %s", exc)
            return None
        hold = None
        # Phase 5: feed external endpoints referenced by the result
        # to the kill-chain scorer: a result steering the session to
        # a fresh external endpoint after access/staging progress is
        # an exfiltration-stage observation. A chain completed here
        # at block level HOLDS the response (Phase 5 decision,
        # 2026-10-23): the caller receives the signed kill-chain
        # block instead of the result. The block also feeds
        # quarantine, mirroring the threat-intel path below.
        if self.server.kill_chain.enabled and corr is not None:
            try:
                from urllib.parse import urlsplit
                indicators = extract_indicators(upstream_resp)
                hosts = sorted({
                    urlsplit(u).hostname or ""
                    for u in indicators.get("urls", [])} - {""})
                if hosts:
                    kc_result = self.server.kill_chain.observe_result(
                        corr["session_key"], hosts, tool_name=tool_name)
                    kc_verdict = kc_result.get("verdict")
                    if kc_verdict in ("flag", "block"):
                        indicators["hosts"] = hosts
                        self._record_kill_chain_outcome(
                            corr, upstream_url, tool_name, kc_result,
                            indicators=indicators, source="result")
                    if kc_verdict == "block":
                        seq_detail = kc_result.get("sequence", {})
                        evidence = [{
                            "type": "kill_chain",
                            "id": f"chain-{seq_detail.get('chain', 1)}",
                            "detail": seq_detail.get("explanation", ""),
                        }]
                        neighbors.flag(
                            upstream_url,
                            f"kill-chain sequence completed by result "
                            f"of '{tool_name}'",
                            [e["detail"] for e in evidence])
                        if quarantine.evaluate(
                                upstream_url, evidence=evidence):
                            self.server.reputation.record_quarantine(
                                upstream_url,
                                "auto-quarantine: kill-chain sequence "
                                "in tool result")
                        log.warning(json.dumps({
                            "event": "kill_chain_result_block",
                            "tool": tool_name,
                            "upstream": upstream_url,
                            "verdict": kc_verdict,
                            "reasons": kc_result.get("reasons", []),
                            "sequence_score": kc_result.get(
                                "risk_score", 0.0),
                        }))
                        hold = {"kc_result": kc_result,
                                "evidence": evidence}
                    elif kc_verdict == "flag":
                        log.warning(json.dumps({
                            "event": "kill_chain_result_flag",
                            "tool": tool_name,
                            "upstream": upstream_url,
                            "verdict": kc_verdict,
                            "reasons": kc_result.get("reasons", []),
                            "sequence_score": kc_result.get(
                                "risk_score", 0.0),
                        }))
            except Exception as exc:
                log.error("kill-chain result hook error: %s", exc)
        # V8 settle hook, false completion: upstream error plus a
        # completion claim in the text that would be delivered.
        # Delivering that claim would be a false completion, the
        # central Eon failure mode. Block it, do not deliver it,
        # and never consume a TAP binding on a post-call block.
        if _is_false_completion(upstream_resp):
            _corr_key = (corr or {}).get("session_key") if isinstance(corr, dict) else None
            _sess = None
            if _corr_key:
                _store = getattr(self.server, "session_bindings", None) or {}
                _sess = _store.get(_corr_key)
            log.warning(json.dumps({
                "event": "settle_outcome",
                "tool": tool_name,
                "upstream": upstream_url,
                "verdict": "block",
                "policy_action": "block_call",
                "system_outcome": "not_completed",
                "reason": "system_refusal",
                "binding_id": (_sess or {}).get("binding_id"),
                "passport_id": (_sess or {}).get("passport_id"),
            }))
            return {"kc_result": {"verdict": "block", "sequence": {}, "reasons": ["system_refusal"]}, "evidence": [{"type": "system_refusal", "id": "false-completion", "detail": "upstream error with completion claim"}]}
        if result_verdict.get("verdict") != "flagged":
            return hold
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
        self.server.telemetry.record(poison_category, "result", [], upstream_url,
                                     upstream_resp)
        neighbors.flag(upstream_url,
                       f"poisoned tool result from '{tool_name}'",
                       [e["detail"] for e in evidence])
        # Phase 3: feed the reputation graph.
        reputation = self.server.reputation
        reputation.record_flag(upstream_url,
                               f"{poison_category}: {tool_name}")
        if result_verdict.get("kit_ids"):
            reputation.record_ti_hit(
                upstream_url,
                f"kit fingerprint: {result_verdict['kit_ids'][0][:20]}...")
        # V8 settle hook, injection quarantine: a flagged result
        # with injection / data leak / malicious indicator is not
        # delivered, even if the existing flag path would deliver
        # it. Quarantine the tool for this session, log the settle
        # outcome, and never consume a TAP binding on quarantine.
        if _is_injection_result(result_verdict):
            _corr_key = (corr or {}).get("session_key") if isinstance(corr, dict) else None
            _sess = None
            if _corr_key:
                _store = getattr(self.server, "session_bindings", None) or {}
                _sess = _store.get(_corr_key)
                _q = getattr(self.server, "session_quarantined_tools", None)
                if _q is None:
                    _q = {}
                    self.server.session_quarantined_tools = _q
                _q.setdefault(_corr_key, set()).add(tool_name)
            log.warning(json.dumps({
                "event": "settle_outcome",
                "tool": tool_name,
                "upstream": upstream_url,
                "verdict": "quarantine",
                "policy_action": "quarantine_tool",
                "system_outcome": "quarantined",
                "reason": "injection_or_poisoned_result",
                "binding_id": (_sess or {}).get("binding_id"),
                "passport_id": (_sess or {}).get("passport_id"),
            }))
            return {"kc_result": {"verdict": "block", "sequence": {}, "reasons": ["injection_or_poisoned_result"]}, "evidence": evidence}
        if quarantine.evaluate(upstream_url, evidence=evidence):
            reputation.record_quarantine(
                upstream_url, "auto-quarantine: poisoned neighbor")
        return hold


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
        # Phase 3: behavioral baselining + server reputation graph.
        self.behavior = BehaviorTracker(enabled=cfg.behavior_enabled)
        self.reputation = ReputationStore()
        # Phase 4: policy enforcement + signed audit trail. The audit
        # trail shares the verdict signer's identity.
        self.policy = PolicyEngine(cfg.policy_file)
        # Phase 5: kill-chain sequence scoring. Toggles come from the
        # policy file's sequence_scoring section when one is present,
        # else from MCP_PROXY_KILL_CHAIN_* environment variables.
        kc_section = self.policy.sequence_scoring_section()
        if kc_section:
            kc_config = SequenceScoringConfig.from_dict(kc_section)
        else:
            kc_config = SequenceScoringConfig.from_env()
        self.kill_chain = KillChainScorer(kc_config)
        # Phase 5 stores: scored-chain history (the /_rs/killchain
        # data source) and corpus-pivot registrations, as JSONL
        # beside the audit file or in the proxy state directory.
        kc_dir = _kill_chain_state_dir(cfg)
        history_path = cfg.kill_chain_history_file or os.path.join(
            kc_dir, "kill_chain_history.jsonl")
        pivots_path = cfg.kill_chain_pivots_file or os.path.join(
            kc_dir, "kill_chain_pivots.jsonl")
        self.kill_chain_history = ChainHistoryStore(history_path)
        self.kill_chain_pivots = PivotRegistry(pivots_path)
        self.schema_store = SchemaStore()
        self.audit = AuditTrail(capacity=cfg.audit_capacity,
                                persist_path=cfg.audit_file)
        # Opt-in telemetry; a no-op object unless MCP_PROXY_TELEMETRY is set.
        self.telemetry = Telemetry.from_config(cfg)
        self.audit.signer = self.signer
        super().__init__(("0.0.0.0", cfg.listen_port), ProxyHandler)
        # Register (and TI-check) the upstream on startup.
        if cfg.upstream_url:
            self.neighbors.register(cfg.upstream_url)
            self.reputation.get_or_create(cfg.upstream_url)


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


# Intent-binding helpers, Item 3, verb classification, not upstream names.
_READ_VERBS = ("list", "get", "read", "search", "describe", "query", "lookup", "check", "view", "show", "find", "count")
_STATE_VERBS = ("create", "update", "delete", "write", "set", "put", "post", "patch", "insert", "remove", "move", "rename", "publish", "send", "pay", "transfer", "refund", "charge", "purchase", "order", "submit", "execute", "run", "upload", "share", "grant", "revoke")
_WRITE_ARGS = ("amount", "amount_minor", "value", "total", "price", "payment_amount", "recipient", "counterparty", "payee", "to", "destination", "destination_address")

def _tool_verb(tool_name):
    name = (tool_name or "").lower()
    for verb in _STATE_VERBS:
        if name == verb or name.startswith(verb + "_") or name.startswith(verb + "-"):
            return verb
    for verb in _READ_VERBS:
        if name == verb or name.startswith(verb + "_") or name.startswith(verb + "-"):
            return verb
    return None

def _tool_is_read_only(tool_name, arguments):
    if tool_name in ("initialize", "tools/list", "ping"):
        return True
    verb = _tool_verb(tool_name)
    if verb in _STATE_VERBS:
        return False
    if isinstance(arguments, dict) and any(k in arguments for k in _WRITE_ARGS):
        return False
    # Unknown tools default to state-changing, fail closed.
    return verb in _READ_VERBS

def _to_minor(amount, currency):
    # Mirrors relayshield_intent_binding.to_minor_units: decimal string to
    # integer minor units. USD and most currencies use 2 decimals, JPY 0.
    # Amounts already in minor units are passed as amount_minor, not here.
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(str(amount).replace(",", ""))
    except (InvalidOperation, ValueError):
        raise ValueError(f"unparseable amount: {amount!r}")
    if value < 0:
        raise ValueError("amount must not be negative")
    exponent = 0 if str(currency or "").upper() in ("JPY", "KRW", "VND") else 2
    return int(value * (10 ** exponent))

def _intent_mismatch(session, tool_name, arguments):
    # Returns a reason code, or None if the call matches the bound intent.
    # Real Gateway fields: payer, counterparty, amount (decimal string),
    # currency, artifacts (list), rail. No tool scope in the binding, so
    # scope is tool class only for general session bindings. Tolerance is
    # policy, not a binding field: default minor 0, bps 0, exact match,
    # unless the session carries amount_tolerance_minor or amount_tolerance_bps.
    args = arguments or {}
    # Payer, if present in arguments and in the binding.
    payer = args.get("payer")
    if payer and session.get("payer") and str(payer).strip().lower() != str(session.get("payer")).strip().lower():
        return "intent_drift_recipient"
    # Recipient, counterparty, first present field wins.
    recipient = None
    for field in ("counterparty", "recipient", "payee", "to", "destination", "customer_id", "account_id", "user_id", "email", "wallet", "address", "target"):
        if args.get(field):
            recipient = str(args.get(field)).strip().lower()
            break
    bound_recipient = session.get("counterparty")
    if recipient and bound_recipient and recipient != str(bound_recipient).strip().lower():
        return "intent_drift_recipient"
    # Currency, if present in arguments and in the binding.
    currency = args.get("currency") or session.get("currency")
    if args.get("currency") and session.get("currency") and str(args.get("currency")).strip().upper() != str(session.get("currency")).strip().upper():
        return "intent_drift_amount"
    # Amount, first present field wins. amount_minor is already minor units,
    # amount and other decimal fields are converted with _to_minor.
    amount_minor = None
    if args.get("amount_minor") is not None:
        try:
            amount_minor = int(args.get("amount_minor"))
        except Exception:
            return "intent_drift_amount"
    else:
        for field in ("amount", "value", "total", "price", "sum", "payment_amount", "charge_amount"):
            if args.get(field) is not None:
                try:
                    amount_minor = _to_minor(args.get(field), currency)
                except Exception:
                    return "intent_drift_amount"
                break
    bound_amount = session.get("amount")
    if amount_minor is not None and bound_amount is not None:
        try:
            bound_minor = _to_minor(bound_amount, session.get("currency"))
        except Exception:
            return "intent_drift_amount"
        tolerance_minor = session.get("amount_tolerance_minor") or 0
        tolerance_bps = session.get("amount_tolerance_bps") or 0
        try:
            tolerance_minor = int(tolerance_minor)
            tolerance_bps = int(tolerance_bps)
        except Exception:
            tolerance_minor, tolerance_bps = 0, 0
        allowed = tolerance_minor + (bound_minor * tolerance_bps // 10000 if bound_minor else 0)
        if abs(amount_minor - bound_minor) > allowed:
            return "intent_drift_amount"
    # Artifacts, if the binding carries artifacts and the call carries an artifact id.
    bound_artifacts = session.get("artifacts") or []
    if bound_artifacts:
        call_artifact = None
        for field in ("artifact_id", "invoice_id", "order_id", "document_id", "file_id", "url", "content_hash"):
            if args.get(field):
                call_artifact = str(args.get(field))
                break
        if call_artifact:
            bound_ids = set()
            for art in bound_artifacts:
                if isinstance(art, dict):
                    for key in ("id", "artifact_id", "hash", "content_hash"):
                        if art.get(key):
                            bound_ids.add(str(art.get(key)))
                elif art:
                    bound_ids.add(str(art))
            if bound_ids and call_artifact not in bound_ids:
                return "intent_scope_expansion"
    # Scope: no tool scope field in the Gateway binding, so no tool-name
    # check is added here. A payment binding only matches payment-like tools
    # by the recipient and amount checks above, and a general session binding
    # matches by tool class only, via _tool_is_read_only and the gate above.
    return None


def _is_false_completion(upstream_resp):
    """True only for error plus completion claim, the false completion pair.

    Unwraps a JSON-RPC response: the MCP result can be the object
    itself, or upstream_resp["result"] if upstream_resp is a wrapped
    JSON-RPC response. Checks isError and error at either level.
    """
    if not isinstance(upstream_resp, dict):
        return False
    candidates = [upstream_resp]
    inner = upstream_resp.get("result")
    if isinstance(inner, dict):
        candidates.append(inner)
    error_present = False
    parts = []
    for obj in candidates:
        if obj.get("error"):
            error_present = True
        if obj.get("isError") is True:
            error_present = True
        for item in obj.get("content", []) or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if isinstance(obj.get("result"), str):
            parts.append(obj["result"])
    if not error_present:
        return False
    text = " ".join(parts).lower()
    claims = ("completed", "successfully", "task complete", "payment sent", "paid successfully", "done")
    return any(word in text for word in claims)


def _is_injection_result(result_verdict):
    """True for a flagged result with injection / leak / malicious signal."""
    if not isinstance(result_verdict, dict):
        return False
    if result_verdict.get("verdict") != "flagged":
        return False
    category = str(result_verdict.get("poison_category", "")).lower()
    if category in ("prompt_injection", "injection", "data_leak", "malicious"):
        return True
    reasons = " ".join(str(r) for r in result_verdict.get("reasons", [])).lower()
    return any(word in reasons for word in ("injection", "prompt injection", "data leak", "exfiltrat", "malicious indicator"))


def _settle_result_outcome(upstream_resp, result_verdict, session=None):
    """Pure settle outcome, for tests and for _screen_result logging.

    Returns a dict with verdict, policy_action, system_outcome, reason,
    or a clean pass dict. Never consumes a TAP binding.
    """
    if _is_false_completion(upstream_resp):
        return {"verdict": "block", "policy_action": "block_call", "system_outcome": "not_completed", "reason": "system_refusal"}
    if _is_injection_result(result_verdict):
        return {"verdict": "quarantine", "policy_action": "quarantine_tool", "system_outcome": "quarantined", "reason": "injection_or_poisoned_result"}
    return {"verdict": "pass", "policy_action": "allow", "system_outcome": "completed", "reason": None}
