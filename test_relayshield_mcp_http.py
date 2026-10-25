#!/usr/bin/env python3
"""relayshield_mcp_http.py must behave exactly like the Hugging Face Space it replaces.

The AWS-hosted MCP endpoint exists because the FTR prerequisite "deployed on
AWS" fails while the listing's MCP endpoint is a Hugging Face Space. It is only
worth anything if a buyer's agent sees the SAME tools returning the SAME results.
So this does not assert shapes it believes in; it loads hf-space-mcp-server/app.py
(gradio stubbed, requests replaced by a fake that serves canned upstream
responses, AWS_MARKETPLACE_MODE=true like the AWS Space) and runs every tool
through both implementations against identical upstream answers.

It also pins what makes the endpoint "on AWS" in the first place: the module
imports only the standard library and calls only api.relayshield.net, so no
third party ever sees a caller's key or query.

No network, no gradio, no AWS. Runs anywhere, including a fresh checkout in CI.
"""

import ast
import base64
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
APP = ROOT / "hf-space-mcp-server" / "app.py"
MODULE = ROOT / "relayshield_mcp_http.py"

sys.path.insert(0, str(ROOT))

# --- the fake upstream both implementations talk to ----------------------

CALLS = []  # (method, url, body) for every request either side made

UPSTREAM = {
    "/v1/metered/mcp-registry-risk": {"verdict": "HIGH", "queried": "evil.example", "findings": [{"type": "typosquat"}]},
    "/v1/metered/prompt-injection-breach": {"found": True, "sessions": [{"severity": "CRITICAL"}, {"severity": "LOW"}]},
    "/v1/metered/tech-stack-cve": {"all_matches": [{"cve_id": "CVE-1"}], "critical_cves": [{"cve_id": "CVE-1"}],
                                   "tech_stack_queried": ["langchain"], "critical_count": 1, "total_matches": 1},
    "/v1/metered/bulk-identity-risk": {"results": [{"domain": "a.com", "domain_risk": "HIGH"}], "critical_count": 0,
                                       "high_count": 1, "queried": 1},
    "/v1/metered/oauth-watchlist": {"matched_apps": [{"app": "x"}], "stolen_tokens": [{"t": 1}],
                                    "highest_severity": "HIGH", "checked_at": "2026-10-25T00:00:00Z"},
    "/v1/metered/supply-chain": {"results": [{"d": "v.com"}], "highest_risk": "HIGH", "critical_vendors": [],
                                 "high_risk_vendors": ["v.com"], "domains_checked": 1, "checked_at": "2026-10-25T00:00:00Z"},
    "/v1/metered/session-risk": {"found": True, "highest_severity": "CRITICAL", "sessions": [{"service_category": "sso"}]},
    "/v1/metered/nhi-exposure": {"found": True, "highest_severity": "HIGH", "findings": [{"type": "pat"}],
                                 "domains_checked": 2, "checked_at": "2026-10-25T00:00:00Z"},
    "/v1/metered/secret-scan": {"found": True, "highest_severity": "HIGH", "findings": [{"severity": "HIGH"}],
                                "domains_checked": 1, "checked_at": "2026-10-25T00:00:00Z"},
    "/v1/metered/llm-credential-exposure": {"findings": [{"p": "openai"}], "providers_affected": ["openai"],
                                            "highest_severity": "CRITICAL", "found": True, "checked_at": "2026-10-25T00:00:00Z"},
    "/v1/metered/breach": {"highest_severity": "HIGH", "breaches": [{"n": "b"}], "breach_count": 1},
}
CLEAN = {
    "/v1/metered/mcp-registry-risk": {"verdict": "NONE", "findings": []},
    "/v1/metered/prompt-injection-breach": {"found": False, "sessions": []},
    "/v1/metered/tech-stack-cve": {"all_matches": [], "critical_cves": []},
    "/v1/metered/bulk-identity-risk": {"results": [], "critical_count": 0, "high_count": 0},
    "/v1/metered/oauth-watchlist": {"matched_apps": [], "stolen_tokens": []},
    "/v1/metered/supply-chain": {"results": [], "highest_risk": "CLEAN", "domains_checked": 1},
    "/v1/metered/session-risk": {"found": False, "sessions": []},
    "/v1/metered/nhi-exposure": {"found": False, "findings": [], "domains_checked": 1},
    "/v1/metered/secret-scan": {"found": False, "findings": [], "domains_checked": 1},
    "/v1/metered/llm-credential-exposure": {"findings": [], "providers_affected": []},
    "/v1/metered/breach": {"breaches": [], "breach_count": 0},
}
TAXII = {"objects": [{"type": "indicator", "id": "indicator--1"}]}

MODE = {"data": UPSTREAM, "status": 200, "timeout": False}


def _upstream(method, url, body):
    """The single source of truth both sides are served from: (status, text)."""
    CALLS.append((method, url, body))
    if MODE["timeout"]:
        raise TimeoutError("fake timeout")
    if MODE["status"] != 200:
        return MODE["status"], "boom body"
    path = url.split("api.relayshield.net", 1)[1].split("?", 1)[0]
    if path == "/developers":
        return 200, "<html>"
    if path.startswith("/v1/intel/taxii"):
        return 200, json.dumps(TAXII)
    return 200, json.dumps({"data": MODE["data"][path]})


class _FakeResp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text

    def json(self):
        return json.loads(self.text)


def _build_fake_requests():
    mod = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    mod.RequestException, mod.Timeout = RequestException, Timeout

    def post(url, json=None, headers=None, timeout=None):
        try:
            return _FakeResp(*_upstream("POST", url, json))
        except TimeoutError:
            raise Timeout("fake")

    def get(url, params=None, headers=None, timeout=None):
        full = url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
        try:
            return _FakeResp(*_upstream("GET", full, None))
        except TimeoutError:
            raise Timeout("fake")

    mod.post, mod.get = post, get
    return mod


def _load_space():
    """app.py exactly as the AWS-marketplace Space runs it, minus gradio."""
    src = APP.read_text(encoding="utf-8")
    mod = types.ModuleType("hf_app_under_test")
    mod.__file__ = str(APP)
    with mock.patch.dict(os.environ, {"AWS_MARKETPLACE_MODE": "true"}), \
            mock.patch.dict(sys.modules, {"gradio": mock.MagicMock(), "requests": _build_fake_requests()}):
        exec(compile(src, str(APP), "exec"), mod.__dict__)
    return mod


SPACE = _load_space()
DEMO_KEY = SPACE._DEMO_API_KEY

import relayshield_mcp_http as LAMBDA  # noqa: E402

REAL_HTTP_REQUEST = LAMBDA._http_request  # kept for the real-socket tests below


def _set(data=UPSTREAM, status=200, timeout=False):
    MODE.update(data=data, status=status, timeout=timeout)
    CALLS.clear()


def _lambda_timeout_aware(*args, **kwargs):
    try:
        return _upstream(*args[:3])
    except TimeoutError:
        raise LAMBDA._Timeout("fake")


LAMBDA._http_request = lambda method, url, body=None, headers=None, timeout=15: _lambda_timeout_aware(method, url, body)

# (tool, arguments) pairs that cover validation, auth and the happy path.
SCENARIOS = [
    ("check_mcp_server_risk", {"server_url": "https://evil.example/mcp", "api_key": "k"}),
    ("check_mcp_server_risk", {"server_url": "", "api_key": "k"}),
    ("check_mcp_server_risk", {"server_url": "https://x", "api_key": ""}),
    ("check_prompt_injection_breach", {"email": "a@b.com", "api_key": "k"}),
    ("check_prompt_injection_breach", {"email": "nope", "api_key": "k"}),
    ("check_tech_stack_cve", {"tech_stack": "langchain, nacos", "api_key": "k"}),
    ("check_tech_stack_cve", {"tech_stack": " , ", "api_key": "k"}),
    ("check_bulk_identity_risk", {"domain": "a.com", "agent_emails": "x@a.com, y@a.com", "api_key": "k"}),
    ("check_bulk_identity_risk", {"domain": "", "agent_emails": "", "api_key": "k"}),
    ("check_oauth_watchlist", {"email": "a@b.com", "api_key": "k"}),
    ("check_supply_chain", {"vendor_domains": "v.com, w.com", "api_key": "k"}),
    ("check_supply_chain", {"vendor_domains": "", "api_key": "k"}),
    ("check_session_risk", {"email": "a@b.com", "api_key": "k"}),
    ("check_nhi_exposure", {"domain": "a.com", "vendor_domains": "", "api_key": "k"}),
    ("check_nhi_exposure", {"domain": "", "vendor_domains": "", "api_key": "k"}),
    ("check_secret_scan", {"domain": "a.com", "vendor_domains": "v.com", "api_key": "k"}),
    ("check_llm_credential_exposure", {"domain": "a.com", "api_key": "k"}),
    ("check_llm_credential_exposure", {"domain": "a.com", "api_key": ""}),
    ("check_llm_credential_exposure", {"domain": "", "api_key": "k"}),
    ("check_agent_risk_summary", {"domain": "a.com", "email": "a@b.com", "tech_stack": "langchain", "api_key": "k"}),
    ("check_agent_risk_summary", {"domain": "", "email": "", "tech_stack": "", "api_key": "k"}),
    ("check_agent_risk_summary", {"domain": "a.com", "email": "", "tech_stack": "", "api_key": ""}),
    ("get_stix_indicators", {"limit": 10, "api_key": "k"}),
    ("get_stix_indicators", {"limit": 0, "api_key": "k"}),
    ("get_stix_indicators", {"limit": 5, "api_key": ""}),
    ("check_server_status", {}),
]


def _call_space(name, args):
    # the Space's own functions, called with the same positional order Gradio would use
    fn = getattr(SPACE, name)
    import inspect
    params = list(inspect.signature(fn).parameters)
    return fn(*[args.get(p, "" if p != "limit" else 0) for p in params])


def _call_lambda(name, args):
    return LAMBDA._run_tool(name, args)


class ParityWithTheSpace(unittest.TestCase):
    def setUp(self):
        os.environ["RS_DEMO_API_KEY"] = DEMO_KEY

    def _assert_all_equal(self, label):
        for name, args in SCENARIOS:
            with self.subTest(label=label, tool=name, args=args):
                _set(*self._state)
                space = _call_space(name, args)
                _set(*self._state)
                mine = _call_lambda(name, args)
                self.assertEqual(json.loads(space), json.loads(mine))

    def test_findings(self):
        self._state = (UPSTREAM, 200, False)
        self._assert_all_equal("findings")

    def test_clean(self):
        clean = dict(CLEAN)
        self._state = (clean, 200, False)
        # tools whose clean path the fixtures cover; the rest use findings above
        for name, args in SCENARIOS:
            if name in ("get_stix_indicators", "check_server_status"):
                continue
            with self.subTest(tool=name):
                _set(clean)
                space = _call_space(name, args)
                _set(clean)
                self.assertEqual(json.loads(space), json.loads(_call_lambda(name, args)))

    def test_upstream_errors_and_timeouts(self):
        for status in (401, 403, 429, 500, 404):
            for name, args in SCENARIOS:
                if name == "check_server_status":
                    continue
                with self.subTest(status=status, tool=name):
                    _set(UPSTREAM, status)
                    space = _call_space(name, args)
                    _set(UPSTREAM, status)
                    self.assertEqual(json.loads(space), json.loads(_call_lambda(name, args)))
        for name, args in SCENARIOS:
            if name == "check_server_status":
                continue
            with self.subTest(timeout=True, tool=name):
                _set(UPSTREAM, 200, True)
                space = _call_space(name, args)
                _set(UPSTREAM, 200, True)
                self.assertEqual(json.loads(space), json.loads(_call_lambda(name, args)))

    def test_tool_manifest_is_the_spaces_manifest(self):
        self.assertEqual(LAMBDA.TOOLS, SPACE._SERVER_CARD["tools"])

    def test_every_manifest_tool_is_dispatchable_and_vice_versa(self):
        self.assertEqual({t["name"] for t in LAMBDA.TOOLS}, set(LAMBDA._DISPATCH))

    def test_requests_carry_the_key_and_the_spaces_source_label(self):
        _set()
        _call_lambda("check_mcp_server_risk", {"server_url": "https://x", "api_key": "abc"})
        captured = {}
        orig = LAMBDA._http_request
        LAMBDA._http_request = lambda m, u, b=None, h=None, t=15: (captured.update(h=h), _upstream(m, u, b))[1]
        try:
            _call_lambda("check_mcp_server_risk", {"server_url": "https://x", "api_key": "abc"})
        finally:
            LAMBDA._http_request = orig
        self.assertEqual(captured["h"]["X-RS-API-KEY"], "abc")
        self.assertEqual(captured["h"]["X-RS-Source"], "hf-mcp-space")


class OnAws(unittest.TestCase):
    """What makes this the thing the FTR prerequisite asks for."""

    def test_imports_only_the_standard_library(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        top = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                top.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top.add(node.module.split(".")[0])
        self.assertTrue(top <= set(sys.stdlib_module_names), f"non-stdlib imports: {top - set(sys.stdlib_module_names)}")

    def test_only_ever_calls_the_relayshield_api(self):
        _set()
        os.environ["RS_DEMO_API_KEY"] = DEMO_KEY
        for name, args in SCENARIOS:
            _call_lambda(name, args)
        self.assertTrue(CALLS)
        for method, url, _ in CALLS:
            self.assertTrue(url.startswith("https://api.relayshield.net/"), url)

    def test_no_signup_link_anywhere_a_buyer_can_read_it(self):
        # AWS's Tier-1 audit failed Bundle D's visibility twice over exactly this.
        blob = json.dumps(LAMBDA.TOOLS)
        _set()
        os.environ["RS_DEMO_API_KEY"] = DEMO_KEY
        for name, args in SCENARIOS:
            blob += _call_lambda(name, {**args, "api_key": ""} if "api_key" in args else args)
        self.assertNotIn("api.relayshield.net/developers", blob)

    def test_demo_key_is_not_copied_into_the_module(self):
        self.assertNotIn(DEMO_KEY, MODULE.read_text(encoding="utf-8"))

    def test_free_tool_without_a_demo_key_asks_for_a_key_instead_of_sending_blank(self):
        _set()
        os.environ.pop("RS_DEMO_API_KEY", None)
        out = json.loads(LAMBDA.check_llm_credential_exposure("a.com", ""))
        self.assertEqual(out["error"]["kind"], "auth")
        self.assertFalse(CALLS)


def _event(method="POST", path="/mcp", body=None, raw=None, b64=False):
    body = raw if raw is not None else (json.dumps(body) if body is not None else "")
    if b64:
        body = base64.b64encode(body.encode()).decode()
    return {"requestContext": {"http": {"method": method}}, "rawPath": path, "body": body, "isBase64Encoded": b64}


def _rpc(method, params=None, id_=1, **kw):
    msg = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        msg["id"] = id_
    if params is not None:
        msg["params"] = params
    return LAMBDA.lambda_handler(_event(body=msg, **kw), None)


# What the AWS listing advertises, plus introspection. tools/create_mcp_http_lambda.sh
# must set RS_MCP_TOOLS to exactly this; a test below reads the script and checks.
AWS_LISTING_TOOLS = {
    "check_mcp_server_risk", "check_prompt_injection_breach", "check_tech_stack_cve",
    "check_bulk_identity_risk", "check_llm_credential_exposure", "check_server_status",
}


def _load_copy(env):
    """A second, independent copy of the module, so the shared one's patched seam survives."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("relayshield_mcp_http_restricted", MODULE)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(mod)
    return mod


class ToolsetRestriction(unittest.TestCase):
    def setUp(self):
        self.mod = _load_copy({"RS_MCP_TOOLS": ",".join(sorted(AWS_LISTING_TOOLS))})

    def test_unset_means_all_thirteen(self):
        self.assertEqual(len(LAMBDA.TOOLS), 13)

    def test_restricted_endpoint_lists_exactly_the_listing_tools(self):
        self.assertEqual({t["name"] for t in self.mod.TOOLS}, AWS_LISTING_TOOLS)
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        out = self.mod.lambda_handler(_event(body=msg), None)
        self.assertEqual({t["name"] for t in json.loads(out["body"])["result"]["tools"]}, AWS_LISTING_TOOLS)

    def test_an_excluded_tool_cannot_be_called_by_name(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "check_supply_chain", "arguments": {"vendor_domains": "a.com", "api_key": "k"}}}
        out = json.loads(self.mod.lambda_handler(_event(body=msg), None)["body"])
        self.assertEqual(out["error"]["code"], -32602)

    def test_server_status_reports_the_restricted_count(self):
        saved = self.mod._http_request
        self.mod._http_request = lambda *a, **k: (200, "<html>")
        try:
            ev = json.loads(self.mod.check_server_status())["evidence"][0]
        finally:
            self.mod._http_request = saved
        self.assertEqual(ev["tool_count"], len(AWS_LISTING_TOOLS))

    def test_a_typo_fails_at_import_not_silently(self):
        with self.assertRaises(RuntimeError):
            _load_copy({"RS_MCP_TOOLS": "check_mcp_server_risk,check_mcp_server_rsik"})

    def test_the_setup_script_sets_exactly_this_list(self):
        script = (ROOT / "tools" / "create_mcp_http_lambda.sh").read_text(encoding="utf-8")
        import re
        m = re.search(r'^TOOLSET="([^"]+)"', script, re.M)
        self.assertIsNotNone(m, "tools/create_mcp_http_lambda.sh must define TOOLSET")
        self.assertEqual(set(m.group(1).split(",")), AWS_LISTING_TOOLS)
        self.assertIn("RS_MCP_TOOLS=$TOOLSET", script)

    def test_no_excluded_tool_is_one_that_the_listing_sells(self):
        excluded = {t["name"] for t in LAMBDA.TOOLS} - AWS_LISTING_TOOLS
        self.assertEqual(len(excluded), 7)
        self.assertTrue(excluded.isdisjoint({"check_mcp_server_risk", "check_prompt_injection_breach",
                                             "check_tech_stack_cve", "check_bulk_identity_risk",
                                             "check_llm_credential_exposure"}))


class RealHttpSeam(unittest.TestCase):
    """_http_request is the one place this module touches the network, and every
    other test replaces it. So run the REAL function against a real local server:
    a fake that returns what the code expects cannot show that urllib returns it."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading
        import time

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self):
                if self.path.startswith("/slow"):
                    time.sleep(1.0)
                code = {"/ok": 200, "/unauth": 401, "/boom": 500}.get(self.path.split("?")[0], 200)
                body = json.dumps({"data": {"echo": self.headers.get("X-RS-API-KEY"), "path": self.path}}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _reply

            def log_message(self, *a):
                pass

        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_success_returns_status_and_body_and_sends_headers_and_json(self):
        status, text = REAL_HTTP_REQUEST("POST", self.base + "/ok", {"a": 1}, {"X-RS-API-KEY": "abc"}, 5)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text)["data"]["echo"], "abc")

    def test_error_statuses_come_back_as_values_not_exceptions(self):
        self.assertEqual(REAL_HTTP_REQUEST("POST", self.base + "/unauth", {}, {}, 5)[0], 401)
        self.assertEqual(REAL_HTTP_REQUEST("POST", self.base + "/boom", {}, {}, 5)[0], 500)

    def test_slow_server_raises_timeout(self):
        with self.assertRaises(LAMBDA._Timeout):
            REAL_HTTP_REQUEST("POST", self.base + "/slow", {}, {}, 0.2)

    def test_refused_connection_raises_net_error(self):
        with self.assertRaises(LAMBDA._NetError):
            REAL_HTTP_REQUEST("POST", "http://127.0.0.1:1/x", {}, {}, 2)

    def test_a_tool_runs_end_to_end_over_a_real_socket(self):
        saved, saved_base = LAMBDA._http_request, LAMBDA.API_BASE_URL
        LAMBDA._http_request, LAMBDA.API_BASE_URL = REAL_HTTP_REQUEST, self.base
        try:
            out = json.loads(LAMBDA.check_mcp_server_risk("https://x", "k"))
            self.assertEqual(out["outcome"], "no_known_finding")
            out = json.loads(LAMBDA.check_server_status())
            self.assertTrue(out["evidence"][0]["upstream_reachable"])
        finally:
            LAMBDA._http_request, LAMBDA.API_BASE_URL = saved, saved_base


class StreamableHttpTransport(unittest.TestCase):
    def setUp(self):
        os.environ["RS_DEMO_API_KEY"] = DEMO_KEY
        _set()

    def test_initialize_negotiates_a_supported_version(self):
        r = _rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}})
        res = json.loads(r["body"])["result"]
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(res["protocolVersion"], "2025-03-26")
        self.assertIn("tools", res["capabilities"])

    def test_unknown_client_version_gets_our_newest(self):
        res = json.loads(_rpc("initialize", {"protocolVersion": "1999-01-01"})["body"])["result"]
        self.assertEqual(res["protocolVersion"], LAMBDA.SUPPORTED_PROTOCOLS[0])

    def test_tools_list_returns_all_thirteen(self):
        tools = json.loads(_rpc("tools/list")["body"])["result"]["tools"]
        self.assertEqual(len(tools), 13)

    def test_tools_call_returns_text_content_and_flags_errors(self):
        ok = json.loads(_rpc("tools/call", {"name": "check_mcp_server_risk",
                                            "arguments": {"server_url": "https://x", "api_key": "k"}})["body"])["result"]
        self.assertFalse(ok["isError"])
        self.assertEqual(json.loads(ok["content"][0]["text"])["outcome"], "finding")
        bad = json.loads(_rpc("tools/call", {"name": "check_mcp_server_risk",
                                             "arguments": {"server_url": "https://x"}})["body"])["result"]
        self.assertTrue(bad["isError"])

    def test_unknown_tool_and_method_are_json_rpc_errors(self):
        self.assertEqual(json.loads(_rpc("tools/call", {"name": "nope"})["body"])["error"]["code"], -32602)
        self.assertEqual(json.loads(_rpc("does/not/exist")["body"])["error"]["code"], -32601)

    def test_notifications_get_202_and_no_body(self):
        r = _rpc("notifications/initialized", id_=None)
        self.assertEqual((r["statusCode"], r["body"]), (202, ""))

    def test_batches_and_base64_bodies(self):
        batch = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}]
        r = LAMBDA.lambda_handler(_event(body=batch, b64=True), None)
        self.assertEqual(json.loads(r["body"]), [{"jsonrpc": "2.0", "id": 1, "result": {}}])

    def test_garbage_is_a_parse_error_not_a_crash(self):
        r = LAMBDA.lambda_handler(_event(raw="{not json"), None)
        self.assertEqual((r["statusCode"], json.loads(r["body"])["error"]["code"]), (400, -32700))

    def test_get_on_the_mcp_path_is_405_and_health_is_200(self):
        self.assertEqual(LAMBDA.lambda_handler(_event("GET", "/mcp"), None)["statusCode"], 405)
        self.assertEqual(LAMBDA.lambda_handler(_event("GET", "/health"), None)["statusCode"], 200)

    def test_options_preflight_allows_cors(self):
        r = LAMBDA.lambda_handler(_event("OPTIONS"), None)
        self.assertEqual(r["statusCode"], 204)
        self.assertIn("Access-Control-Allow-Origin", r["headers"])

    def test_server_card_matches_the_manifest(self):
        r = LAMBDA.lambda_handler(_event("GET", "/.well-known/mcp/server-card.json"), None)
        self.assertEqual(json.loads(r["body"])["tools"], LAMBDA.TOOLS)

    def test_rest_api_proxy_event_shape_is_accepted_too(self):
        event = {"httpMethod": "POST", "path": "/mcp", "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})}
        self.assertEqual(LAMBDA.lambda_handler(event, None)["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
