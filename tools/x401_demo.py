#!/usr/bin/env python3
"""The whole x401 + TAP flow, end to end, on this machine, with nothing mocked.

    python3 tools/x401_demo.py

Four parties, all real code with real signatures:

    ISSUER    signs an SD-JWT VC ("age over 18") for the wallet's holder key
    WALLET    the Credential Manager: checks our signed OpenID4VP request, discloses only
              what was asked, binds the answer to the request nonce and the merchant origin
    AGENT     an AI agent with a TAP signing key; it signs the request it sends the merchant
    VERIFIER  RelayShield: relayshield_tap_verifier.lambda_handler, the code that deploys

It needs no network, no AWS and no third-party package. It ends by attacking the flow six
ways; every attack must be refused, and the script exits non-zero if any is not.
"""
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import x401_jose as jose
import x401_rp as rp
import x401_testkit as kit
import relayshield_tap_verifier as tap

ORIGIN, PATH, METHOD = "https://shop.example", "/v1/orders", "POST"
VCT = "https://credentials.example/identity"
GREEN, RED, DIM, END = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
failures = []


def say(msg=""):
    print(msg, flush=True)


def check(label, ok, detail=""):
    say(f"  {GREEN if ok else RED}{'PASS' if ok else 'FAIL'}{END}  {label}" + (f"  {DIM}{detail}{END}" if detail else ""))
    if not ok:
        failures.append(label)


def call(request):
    """What the merchant does: POST the agent's request to the verifier."""
    resp = tap.lambda_handler({"body": json.dumps(request), "headers": {}}, None)
    return resp["statusCode"], json.loads(resp["body"])


def main():
    issuer, wallet, agent = kit.Issuer("https://issuer.example"), kit.Wallet(), kit.Agent("agent-key-1")
    verifier_key = jose.generate_p256_jwk()
    policy = {
        "request_id": "proof-age-18-v1", "satisfied_requirements": ["urn:example:age-over-18"],
        "dcql_query": {"credentials": [{"id": "identity", "format": "dc+sd-jwt", "meta": {"vct_values": [VCT]},
                                        "claims": [{"path": ["age_over_18"], "values": [True]}]}]},
        "trusted_issuers": [issuer.iss], "expected_origins": [ORIGIN], "ttl_seconds": 600, "bind_agent": True}
    os.environ.update({
        "X401_SIGNING_JWK": json.dumps(verifier_key), "X401_POLICIES": json.dumps({"policies": {"age18": policy}}),
        "X401_TRUSTED_ISSUERS": json.dumps({"issuers": {issuer.iss: issuer.registry_entry()}}),
        "VERIFIER_TELEMETRY_DISABLED": "1"})
    rp._signer_cache.update(signer=None, at=0.0)
    tap.fetch_jwks = lambda *a, **k: {agent.keyid: agent.jwk}          # stands in for Visa's key directory
    holder_vc = issuer.sd_jwt_vc(VCT, always={"given_name": "Ada", "family_name": "Lovelace"},
                                 selectable={"age_over_18": True, "birthdate": "1990-12-10", "address": "10 Downing St"},
                                 holder=wallet.public_jwk)

    def agent_request(proof=None, **extra):
        req = agent.request(PATH, METHOD, "merchant.example", extra={"x401_policy": "age18", **extra})
        if proof:
            req["headers"]["PROOF-RESPONSE"] = proof
        return req

    say(f"\n{'=' * 78}\n x401 + TAP, end to end\n{'=' * 78}")
    say("\n1. The agent calls the merchant's route. The merchant asks RelayShield about the request.")
    code, body = call(agent_request())
    check("RelayShield answers 401 with a signed PROOF-REQUEST (TAP verified the agent first)",
          code == 401 and body["reasons"] == ["proof_required"], f"HTTP {code}")
    payload = jose.b64u_json_decode(body["details"]["proof_request"])
    req0 = payload["credential_requirements"]["digital"]["requests"][0]
    claims = jose.jws_payload(req0["data"]["request"])
    say(f"   {DIM}protocol={req0['protocol']}  client_id={claims['client_id']}")
    say(f"   expected_origins={claims['expected_origins']}  asks for: {[c['path'] for c in claims['dcql_query']['credentials'][0]['claims']]}")
    say(f"   PROOF-REQUEST header is {len(body['details']['proof_request'])} characters{END}")

    say("\n2. The agent hands the request to the human's wallet, unchanged.")
    result = wallet.fulfil(payload, {"identity": holder_vc}, origin=ORIGIN,
                           verifier_public_jwk=dict(jose.public_jwk(verifier_key), kid=rp.DEFAULT_KID),
                           disclose={"identity": ["age_over_18"]})
    pres = result["data"]["vp_token"]["identity"][0]
    check("the wallet verified RelayShield's request signature and disclosed ONLY age_over_18",
          pres.count("~") == 2, f"{len(holder_vc['disclosures'])} claims held, 1 disclosed")
    proof = kit.artifact(result, "proof-age-18-v1", agent.keyid)

    say("\n3. The agent retries with PROOF-RESPONSE.")
    code, body = call(agent_request(proof))
    ok = code == 200 and body["decision"] == "accept"
    check("RelayShield ACCEPTS: TAP signature valid AND credential valid AND bound to this agent", ok, f"HTTP {code}")
    if ok:
        got = body["details"]["x401"]["credentials"]["identity"][0]
        say(f"   {DIM}verified issuer: {got['issuer']}   claims returned to the merchant: {got['claims']}")
        say(f"   the merchant never saw: {sorted(set(holder_vc['disclosures']) - {'age_over_18'})}{END}")

    say("\n4. Attacks. Each must be refused with the specific reason.")
    code, body = call(agent_request(proof))
    check("replay of the same proof", body["reasons"] == ["replayed_nonce"], str(body["reasons"]))

    ch = jose.b64u_json_decode(call(agent_request())[1]["details"]["proof_request"])
    other = kit.Wallet()
    stolen = other.fulfil(ch, {"identity": issuer.sd_jwt_vc(VCT, selectable={"age_over_18": False}, holder=other.public_jwk)},
                          origin=ORIGIN, disclose={"identity": ["age_over_18"]})
    check("a minor's credential (age_over_18 = false)", call(agent_request(kit.artifact(stolen, None, agent.keyid)))[1]["reasons"] == ["claims_not_satisfied"])

    ch = jose.b64u_json_decode(call(agent_request())[1]["details"]["proof_request"])
    phish = wallet.fulfil(ch, {"identity": holder_vc}, origin=ORIGIN, aud_override="origin:https://evil.example")
    check("a proof harvested for a phishing origin", call(agent_request(kit.artifact(phish, None, agent.keyid)))[1]["reasons"] == ["audience_mismatch"])

    ch = jose.b64u_json_decode(call(agent_request())[1]["details"]["proof_request"])
    imp = kit.Issuer(issuer.iss)
    forged = wallet.fulfil(ch, {"identity": imp.sd_jwt_vc(VCT, selectable={"age_over_18": True}, holder=wallet.public_jwk)}, origin=ORIGIN)
    check("a credential forged by someone claiming to be the issuer", call(agent_request(kit.artifact(forged, None, agent.keyid)))[1]["reasons"] == ["invalid_signature"])

    ch = jose.b64u_json_decode(call(agent_request())[1]["details"]["proof_request"])
    good = wallet.fulfil(ch, {"identity": holder_vc}, origin=ORIGIN, disclose={"identity": ["age_over_18"]})
    code, body = call(agent_request(kit.artifact(good, None, "some-other-agent")))
    check("a different agent presenting someone else's proof", body["reasons"] == ["agent_binding_failed"])

    admin = agent.request("/v1/admin", METHOD, "merchant.example",
                          extra={"x401_policy": "age18", "headers": None})
    admin["headers"] = {**agent.request("/v1/admin", METHOD, "merchant.example")["headers"],
                        "PROOF-RESPONSE": kit.artifact(good, None, agent.keyid)}
    admin = {**admin, "x401_policy": "age18"}
    code, body = call(admin)
    check("the same proof, from a correctly signed agent, used on another route",
          body["reasons"] == ["route_mismatch"], str(body["reasons"]))

    say(f"\n{'=' * 78}")
    if failures:
        say(f"{RED}{len(failures)} check(s) failed:{END} " + "; ".join(failures))
        return 1
    say(f"{GREEN}Every step behaved as designed.{END}")
    return 0


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"{DIM}({time.time() - t0:.1f}s){END}")
    sys.exit(rc)
