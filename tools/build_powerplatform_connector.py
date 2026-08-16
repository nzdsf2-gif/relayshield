#!/usr/bin/env python3
"""Generate a Power Platform custom connector definition from the live OpenAPI spec.

Run:  python3 tools/build_powerplatform_connector.py
Out:  powerplatform_connector/relayshield_swagger2.json
      powerplatform_connector/apiProperties.json

WHY THIS IS A SEPARATE ARTIFACT AND NOT A CHANGE TO THE SPEC.

Power Platform custom connectors require **OpenAPI 2.0 (Swagger)**. Microsoft
states plainly that OpenAPI 3.0 definitions "are not supported", and
api.relayshield.net/openapi.json is 3.1.0. The temptation is to downgrade the
served spec so one file serves everyone. Do not: 3.1 is what the MCP server, the
published SDKs, the Security Store agent plugin spec and /docs all consume, and
downgrading to satisfy one channel would degrade every other one.

So this DERIVES a 2.0 definition. The 3.1 spec stays the source of truth, this
runs against it, and a drift check is the same one-command story as build_guides.

THREE CONSTRAINTS THAT SHAPE THE OUTPUT.

1. Definition must be under 1 MB. The full 62-operation spec is 279 KB as 3.1
   and grows on conversion, but the real reason to subset is usability: a
   62-action connector is hostile in a flow picker.
2. "If there are multiple security definitions, the custom connector picks the
   top security definition." We publish three. Shipping all three would let the
   wizard silently choose, so this emits exactly ONE.
3. x-ms-summary drives the field labels in the flow designer. Without it every
   input renders as its raw JSON property name.
"""
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "powerplatform_connector")
SPEC_URL = "https://api.relayshield.net/openapi.json"

# Curated for a Power Automate audience: IT ops, MSPs and security teams wiring
# checks into onboarding, offboarding, ticketing and mail flows. Chosen for
# "obvious as a flow step", not for breadth. The payg surface is used rather than
# metered because it needs no separate subscription to start.
OPERATIONS = [
    ("/v1/payg/breach",               "CheckEmailBreach",      "Check email for breach exposure"),
    ("/v1/payg/infostealer",          "CheckInfostealer",      "Check email in infostealer logs"),
    ("/v1/payg/sim-swap",             "CheckSimSwap",          "Check phone number for SIM swap"),
    ("/v1/payg/domain",               "CheckDomainLookalikes", "Find phishing lookalike domains"),
    ("/v1/payg/scan-url",             "ScanUrl",               "Scan a URL for phishing or malware"),
    ("/v1/payg/supply-chain",         "CheckSupplyChain",      "Assess vendor breach risk"),
    ("/v1/payg/ransomware-risk",      "CheckRansomwareRisk",   "Check domain on ransomware leak sites"),
    ("/v1/payg/identity-risk-score",  "GetIdentityRiskScore",  "Score a domain for identity risk"),
    ("/v1/payg/secret-scan-text",     "ScanTextForSecrets",    "Scan text or a diff for secrets"),
    ("/v1/payg/session-risk",         "CheckSessionRisk",      "Check for stolen session cookies"),
    ("/v1/payg/nhi-exposure",         "CheckMachineCredentials", "Find exposed machine credentials"),
    ("/v1/payg/oauth-watchlist",      "CheckOauthTokens",      "Find exposed OAuth and SaaS tokens"),
]


def humanise(name: str) -> str:
    """property_name -> Property name, for x-ms-summary."""
    return name.replace("_", " ").replace("-", " ").strip().capitalize()


def to_swagger2(node):
    """Recursively rewrite a 3.1 schema fragment into 2.0-compatible form."""
    if isinstance(node, list):
        return [to_swagger2(v) for v in node]
    if not isinstance(node, dict):
        return node

    out = {}
    for k, v in node.items():
        if k == "$ref" and isinstance(v, str):
            out[k] = v.replace("#/components/schemas/", "#/definitions/")
            continue
        # 3.1 allows a type ARRAY, including "null". 2.0 allows a single string.
        if k == "type" and isinstance(v, list):
            concrete = [t for t in v if t != "null"]
            out["type"] = concrete[0] if concrete else "string"
            if "null" in v:
                out["x-nullable"] = True
            continue
        # Keywords 2.0 has no concept of. Dropping them is safe; leaving them in
        # makes the connector wizard's validator complain.
        if k in ("examples", "const", "contentMediaType", "unevaluatedProperties",
                 "prefixItems", "$schema", "discriminator", "anyOf", "oneOf"):
            continue
        if k == "nullable":
            out["x-nullable"] = v
            continue
        out[k] = to_swagger2(v)

    # Field labels for the flow designer.
    if out.get("type") == "object" and isinstance(out.get("properties"), dict):
        for pname, pschema in out["properties"].items():
            if isinstance(pschema, dict) and "x-ms-summary" not in pschema and "$ref" not in pschema:
                pschema["x-ms-summary"] = humanise(pname)
    return out


def collect_refs(node, acc):
    if isinstance(node, list):
        for v in node:
            collect_refs(v, acc)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/definitions/"):
                acc.add(v.rsplit("/", 1)[-1])
            else:
                collect_refs(v, acc)


def main():
    with urllib.request.urlopen(SPEC_URL, timeout=30) as r:
        spec = json.loads(r.read().decode("utf-8"))
    if not str(spec.get("openapi", "")).startswith("3."):
        sys.exit("expected an OpenAPI 3.x source, got %r" % spec.get("openapi"))

    src_schemas = (spec.get("components") or {}).get("schemas") or {}
    paths, missing = {}, []

    for path, op_id, summary in OPERATIONS:
        src = (spec.get("paths") or {}).get(path, {}).get("post")
        if not src:
            missing.append(path)
            continue

        params = []
        body_schema = (((src.get("requestBody") or {}).get("content") or {})
                       .get("application/json") or {}).get("schema")
        if body_schema:
            params.append({
                "name": "body",
                "in": "body",
                "required": True,
                "schema": to_swagger2(body_schema),
            })

        responses = {}
        for code, resp in (src.get("responses") or {}).items():
            entry = {"description": resp.get("description") or "Response"}
            rs = ((resp.get("content") or {}).get("application/json") or {}).get("schema")
            if rs:
                entry["schema"] = to_swagger2(rs)
            responses[str(code)] = entry
        responses.setdefault("200", {"description": "Success"})

        paths[path] = {"post": {
            "operationId":  op_id,
            "summary":      summary,
            # The designer shows description under the action name, so carry the
            # richer text from the source spec where there is one.
            "description":  (src.get("description") or summary).strip()[:900],
            "consumes":     ["application/json"],
            "produces":     ["application/json"],
            "parameters":   params,
            "responses":    responses,
        }}

    # Pull in only the definitions the curated subset actually references,
    # transitively, so the file stays small.
    needed, seen = set(), set()
    collect_refs(paths, needed)
    definitions = {}
    while needed - seen:
        name = (needed - seen).pop()
        seen.add(name)
        if name in src_schemas:
            definitions[name] = to_swagger2(src_schemas[name])
            collect_refs(definitions[name], needed)

    swagger = {
        "swagger": "2.0",
        "info": {
            "title":       "RelayShield",
            "description": ("Identity-layer threat intelligence for your flows. Check emails, "
                            "domains, phone numbers and URLs against breach, infostealer and "
                            "criminal-marketplace data before granting access or trusting a message."),
            "version":     "1.0.0",
            "contact":     {"name": "RelayShield Support", "email": "support@relayshield.net"},
        },
        "host":     "api.relayshield.net",
        "basePath": "/",
        "schemes":  ["https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        # EXACTLY ONE. The connector silently takes the first if there are several.
        "securityDefinitions": {
            "api_key": {"type": "apiKey", "in": "header", "name": "X-RS-API-KEY"}
        },
        "security":    [{"api_key": []}],
        "paths":       paths,
        "definitions": definitions,
    }

    api_properties = {
        "properties": {
            "connectionParameters": {
                "api_key": {
                    "type": "securestring",
                    "uiDefinition": {
                        "displayName": "RelayShield API key",
                        "description": "Your RelayShield API key from api.relayshield.net/developers",
                        "tooltip":     "Provide your RelayShield API key",
                        "constraints": {"tabIndex": 2, "clearText": False, "required": "true"},
                    },
                }
            },
            "iconBrandColor": "#6c63ff",
            "capabilities":   [],
            "policyTemplateInstances": [],
        }
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    sw_path = os.path.join(OUT_DIR, "relayshield_swagger2.json")
    ap_path = os.path.join(OUT_DIR, "apiProperties.json")
    with io.open(sw_path, "w", encoding="utf-8") as fh:
        json.dump(swagger, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with io.open(ap_path, "w", encoding="utf-8") as fh:
        json.dump(api_properties, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    size = os.path.getsize(sw_path)
    print("source spec      : OpenAPI %s, %d paths" % (spec["openapi"], len(spec.get("paths", {}))))
    print("connector        : Swagger 2.0, %d operations, %d definitions" % (len(paths), len(definitions)))
    print("size             : %.0f KB  (limit 1024 KB) %s" % (size / 1024, "OK" if size < 1024 * 1024 else "TOO BIG"))
    print("security schemes : 1 (api_key, header X-RS-API-KEY)")
    if missing:
        print("MISSING from the source spec: %s" % ", ".join(missing))
        return 1
    print("wrote %s" % sw_path)
    print("wrote %s" % ap_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
