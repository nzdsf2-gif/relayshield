"""Derive a Power Platform (Swagger 2.0) connector from the OpenAPI 3.1 contract."""
import json, copy, importlib.util, collections, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OPS = [
    ("/v1/metered/breach",              "CheckEmailBreach",     "Check an email for data breach exposure"),
    ("/v1/metered/sim-swap",            "CheckSimSwap",         "Check a phone number for a recent SIM swap"),
    ("/v1/metered/domain",              "CheckLookalikeDomains","Find lookalike domains impersonating a domain"),
    ("/v1/metered/oauth-watchlist",     "CheckOAuthWatchlist",  "Check an email for risky OAuth app grants and stolen tokens"),
    ("/v1/metered/infostealer",         "CheckInfostealer",     "Check an email for infostealer malware exposure"),
    ("/v1/metered/supply-chain",        "CheckVendorRisk",      "Score vendor domains for third-party breach risk"),
    ("/v1/metered/secret-scan-text",    "ScanTextForSecrets",   "Scan text for leaked API keys and credentials"),
    ("/v1/metered/session-risk",        "CheckSessionRisk",     "Check an email for stolen active session cookies"),
    ("/v1/metered/identity-risk-score", "GetIdentityRiskScore", "Get a combined identity risk score for an email"),
    ("/v1/metered/cert-expiry",         "CheckCertificateExpiry","Check TLS certificate expiry for a domain"),
    ("/v1/metered/card-exposure",       "CheckCardExposure",    "Check a BIN or card range for carding-market exposure"),
    ("/v1/metered/ip-intel",            "CheckIpReputation",    "Check an IP address for malicious reputation"),
]

sm = importlib.util.spec_from_file_location(
    "rs_spec", os.path.join(ROOT, "relayshield_openapi_spec.py"))
m = importlib.util.module_from_spec(sm); sm.loader.exec_module(m)
src = m.build_spec()

used_defs = set()

def down(node):
    """OpenAPI 3.1 subschema -> Swagger 2.0 subschema."""
    if isinstance(node, list):
        return [down(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "$ref":
            name = v.rsplit("/", 1)[-1]
            used_defs.add(name)
            out[k] = "#/definitions/" + name
        elif k == "examples":
            # Swagger 2.0 has singular `example`
            if isinstance(v, list) and v:
                out["example"] = v[0]
        elif k in ("const",):
            out["enum"] = [v]
        elif k == "type" and isinstance(v, list):
            non_null = [t for t in v if t != "null"]
            out["type"] = non_null[0] if non_null else "string"
            if "null" in v:
                out["x-nullable"] = True
        elif k in ("prefixItems", "unevaluatedProperties", "$schema", "contentMediaType", "deprecated"):
            continue
        elif k in ("oneOf", "anyOf"):
            # Swagger 2.0 has no oneOf/anyOf: collapse to the first concrete branch.
            branches = [b for b in v if isinstance(b, dict)]
            if branches:
                out.update(down(branches[0]))
        else:
            out[k] = down(v)
    return out

paths = {}
for path, op_id, summary in OPS:
    src_op = src["paths"][path]["post"]
    body_schema = (src_op.get("requestBody", {}).get("content", {})
                          .get("application/json", {}).get("schema", {}))
    resp = (src_op.get("responses", {}).get("200", {}).get("content", {})
                  .get("application/json", {}).get("schema", {}))
    desc = (src_op.get("description") or summary).strip()
    paths[path] = {
        "post": {
            "operationId": op_id,
            "summary": summary,
            "description": desc if len(desc) <= 500 else desc[:497] + "...",
            "x-ms-visibility": "important",
            "consumes": ["application/json"],
            "produces": ["application/json"],
            "parameters": [{
                "name": "body",
                "in": "body",
                "required": True,
                "schema": down(body_schema),
            }],
            "responses": {
                "200": {"description": "Success", "schema": down(resp)},
                "400": {"description": "Bad request. The parameters were missing or malformed."},
                "401": {"description": "Unauthorized. The API key is missing or invalid."},
                "402": {"description": "Payment required. The account has no remaining balance or active plan."},
                "429": {"description": "Too many requests. Slow down and retry."},
                "500": {"description": "Internal server error."},
            },
        }
    }

# Pull in only the definitions actually reachable, transitively.
src_defs = src.get("components", {}).get("schemas", {})
definitions, frontier = {}, set(used_defs)
while frontier:
    name = frontier.pop()
    if name in definitions or name not in src_defs:
        continue
    used_defs.clear()
    definitions[name] = down(src_defs[name])
    frontier |= (used_defs - set(definitions))

swagger = collections.OrderedDict([
    ("swagger", "2.0"),
    ("info", {
        "title": "RelayShield",
        "description": (
            "Identity threat intelligence for security and IT operations. Check whether an email, "
            "phone number, domain, vendor or IP has been exposed in a breach, an infostealer log, a "
            "SIM swap or a criminal marketplace, and act on the result inside your existing flows."
        ),
        "version": "1.0",
        "contact": {"name": "RelayShield Support", "email": "support@relayshield.net",
                    "url": "https://api.relayshield.net/developers"},
        "x-ms-api-annotation": {"status": "Production"},
    }),
    ("host", "api.relayshield.net"),
    ("basePath", "/"),
    ("schemes", ["https"]),
    ("consumes", ["application/json"]),
    ("produces", ["application/json"]),
    ("paths", paths),
    ("definitions", definitions),
    ("securityDefinitions", {"api_key": {"type": "apiKey", "in": "header", "name": "x-api-key"}}),
    ("security", [{"api_key": []}]),
    ("tags", []),
])

def label(name):
    s = re.sub(r"[_\-]+", " ", name).strip()
    s = re.sub(r"(?<!^)(?=[A-Z])", " ", s)
    return " ".join(w if w.isupper() else w.capitalize() for w in s.split())


# x-ms-summary is what the Power Automate designer shows as the field label.
for _op in paths.values():
    for _n, _p in (_op["post"]["parameters"][0].get("schema", {}).get("properties") or {}).items():
        if isinstance(_p, dict):
            _p.setdefault("x-ms-summary", label(_n))

with open(os.path.join(HERE, "apiDefinition.swagger.json"), "w") as f:
    json.dump(swagger, f, indent=2)
    f.write("\n")

print("operations:", len(paths), "| definitions:", len(definitions))
