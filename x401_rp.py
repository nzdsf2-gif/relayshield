"""x401_rp -- a relying-party (Verifier) implementation of x401 0.2.0.

This is the current draft's model, not the old one: the VERIFIER composes and signs an
OpenID4VP request, the agent obtains a credential result for it, and the verifier validates
that result against the request it issued. Source specs read for this build:
    x401           https://github.com/proof/x401  (spec.md, version 0.2.0)
    OpenID4VP 1.0 https://github.com/openid/OpenID4VP  (1.0 draft, errata set 1)

WHAT IT DOES
  create_challenge()   builds the PROOF-REQUEST payload: a JWS-signed OpenID4VP request
                       (or an unsigned one) carrying a DCQL query and a stateless,
                       HMAC-protected nonce that encodes policy, route, method and expiry.
  verify_result()      validates a PROOF-RESPONSE Result Artifact: format, request-bound
                       nonce, signed/unsigned binding, issuer signature, holder key
                       binding, DCQL satisfaction (claims AND value matching, enforced by
                       US because the spec says never to rely on the wallet), issuer
                       trust, credential status, single use.
  error_object()       builds the PROOF-RESULT x401 Error Object.

CREDENTIAL FORMATS: `dc+sd-jwt` (IETF SD-JWT VC, with selective disclosure and a
Key Binding JWT) and `jwt_vc_json` (W3C VC as a JWT, in a holder-signed VP JWT).
NOT SUPPORTED, AND REFUSED RATHER THAN IGNORED: `mso_mdoc` (needs CBOR, COSE and X.509
chain validation), `ldp_vc`, response encryption (`dc_api.jwt`), the OAuth token-exchange
leg, and trust resolution through `openid_federation` / `etsi_tl` / `aki`. A policy naming
an unsupported format fails to load; an encrypted response gets an error object.

TRUST IS OURS, NOT THE WALLET'S. Issuers are accepted only if they appear in the policy's
`trusted_issuers` AND the registry holds a key for them. The request's DCQL
`trusted_authorities` is a hint to the wallet; it is never what we enforce.

NO STATE BUT ONE: the nonce is self-contained (route, method, policy and expiry under an
HMAC), so a challenge and its verification can land on different Lambda containers. The
only shared state is a single-use store (relayshield_verifier_nonces) consulted LAST, after
everything else passed, so a bad result cannot burn a good nonce.
"""

import base64
import hashlib
import hmac
import json
import re
import time
import zlib

import x401_jose as jose

X401_VERSION = "0.2.0"
CLOCK_SKEW = 60
MAX_RESULT_BYTES = 256 * 1024
SUPPORTED_FORMATS = ("dc+sd-jwt", "jwt_vc_json")
UNSUPPORTED_FORMATS = ("mso_mdoc", "ldp_vc", "vc+sd-jwt-ld", "dc+sd-jwt-ld")
ISSUER_ALGS = ("ES256", "EdDSA", "PS256")
PROTOCOL_SIGNED = "openid4vp-v1-signed"
PROTOCOL_UNSIGNED = "openid4vp-v1-unsigned"
DEFAULT_CLIENT_ID = "decentralized_identifier:did:web:api.relayshield.net"
DEFAULT_KID = "did:web:api.relayshield.net#x401-1"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class X401Error(Exception):
    """A proof failure. `code` is the Error Object's `error`; `issuer` is whatever issuer
    the presentation CLAIMED (unverified; telemetry hashes it, nothing trusts it)."""

    def __init__(self, code, description="", issuer=""):
        super().__init__(code)
        self.code, self.description, self.issuer = code, description, issuer


# =========================================================================== policy


def validate_policy(policy_id, policy):
    """Raises ValueError with a precise message. Policies are config, but config is
    input too: a typo here would silently weaken verification."""
    if not isinstance(policy, dict):
        raise ValueError(f"{policy_id}: policy must be an object")
    dcql = policy.get("dcql_query")
    if not isinstance(dcql, dict) or not isinstance(dcql.get("credentials"), list) or not dcql["credentials"]:
        raise ValueError(f"{policy_id}: dcql_query.credentials must be a non-empty array")
    if len(dcql["credentials"]) > 10:
        raise ValueError(f"{policy_id}: at most 10 credential queries")
    ids = set()
    for cq in dcql["credentials"]:
        if not isinstance(cq, dict) or not _ID_RE.match(str(cq.get("id", ""))):
            raise ValueError(f"{policy_id}: each credential query needs an id of [A-Za-z0-9_-]")
        if cq["id"] in ids:
            raise ValueError(f"{policy_id}: duplicate credential id {cq['id']}")
        ids.add(cq["id"])
        fmt = cq.get("format")
        if fmt in UNSUPPORTED_FORMATS or fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"{policy_id}: format {fmt!r} is not supported by this verifier "
                             f"(supported: {', '.join(SUPPORTED_FORMATS)})")
        if cq.get("require_cryptographic_holder_binding") is False:
            raise ValueError(f"{policy_id}: presentations without holder binding are not supported: "
                             "they cannot be bound to the request nonce, so they cannot be replay-protected")
        meta = cq.get("meta")
        if not isinstance(meta, dict):
            raise ValueError(f"{policy_id}: meta is required")
        if fmt == "dc+sd-jwt" and not (isinstance(meta.get("vct_values"), list) and meta["vct_values"]
                                       and all(isinstance(v, str) for v in meta["vct_values"])):
            raise ValueError(f"{policy_id}: dc+sd-jwt needs meta.vct_values")
        if fmt == "jwt_vc_json" and not (isinstance(meta.get("type_values"), list) and meta["type_values"]):
            raise ValueError(f"{policy_id}: jwt_vc_json needs meta.type_values")
        claims = cq.get("claims")
        if claims is not None:
            if not isinstance(claims, list) or not claims or len(claims) > 50:
                raise ValueError(f"{policy_id}: claims must be a non-empty array of at most 50")
            for c in claims:
                p = c.get("path") if isinstance(c, dict) else None
                if not (isinstance(p, list) and p and all(isinstance(s, str) or s is None
                                                          or (isinstance(s, int) and not isinstance(s, bool) and s >= 0)
                                                          for s in p)):
                    raise ValueError(f"{policy_id}: a claim path must be a non-empty array of strings, nulls and indexes")
                if "values" in c and not (isinstance(c["values"], list) and c["values"]):
                    raise ValueError(f"{policy_id}: claim values must be a non-empty array")
        if cq.get("claim_sets") is not None:
            if claims is None or not isinstance(cq["claim_sets"], list) or not cq["claim_sets"]:
                raise ValueError(f"{policy_id}: claim_sets needs claims")
            cids = {c.get("id") for c in claims}
            for cs in cq["claim_sets"]:
                if not isinstance(cs, list) or not cs or any(i not in cids for i in cs):
                    raise ValueError(f"{policy_id}: claim_sets must reference claim ids")
    for cset in dcql.get("credential_sets") or []:
        opts = cset.get("options") if isinstance(cset, dict) else None
        if not (isinstance(opts, list) and opts and all(isinstance(o, list) and o and all(i in ids for i in o) for o in opts)):
            raise ValueError(f"{policy_id}: credential_sets must reference credential ids")
    issuers = policy.get("trusted_issuers")
    if not (isinstance(issuers, list) and issuers and all(isinstance(i, str) and i for i in issuers)):
        raise ValueError(f"{policy_id}: trusted_issuers must be a non-empty array of issuer ids")
    mode = policy.get("mode", "signed")
    if mode not in ("signed", "unsigned", "both"):
        raise ValueError(f"{policy_id}: mode must be signed, unsigned or both")
    if mode in ("signed", "both"):
        origins = policy.get("expected_origins")
        if not (isinstance(origins, list) and origins and all(_ok_origin(o) for o in origins)):
            raise ValueError(f"{policy_id}: signed mode needs expected_origins (https origins)")
    if mode in ("unsigned", "both"):
        origins = policy.get("unsigned_allowed_origins")
        if not (isinstance(origins, list) and origins and all(_ok_origin(o) for o in origins)):
            raise ValueError(f"{policy_id}: unsigned mode needs unsigned_allowed_origins; without a "
                             "declared origin an unsigned result binds to nothing but the nonce")
    ttl = policy.get("ttl_seconds", 600)
    if not (isinstance(ttl, int) and not isinstance(ttl, bool) and 30 <= ttl <= 3600):
        raise ValueError(f"{policy_id}: ttl_seconds must be 30..3600")
    return True


def _ok_origin(o):
    return isinstance(o, str) and re.match(r"^https://[A-Za-z0-9.-]+(:\d{1,5})?$", o) is not None


def load_policies(raw=None, path=None, env=None):
    """{policy_id: policy}. Env X401_POLICIES (JSON) wins, else x401_policies.json beside
    this module. A policy that fails validation is dropped with its reason in the log and
    is therefore NOT AVAILABLE: a broken policy must never become a weaker one."""
    import logging
    import os
    log = logging.getLogger()
    raw = raw if raw is not None else (env if env is not None else os.environ.get("X401_POLICIES", ""))
    if not raw:
        p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "x401_policies.json")
        try:
            with open(p, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
    try:
        doc = json.loads(raw) if raw else {}
        entries = doc.get("policies", {}) if isinstance(doc, dict) else {}
    except ValueError:
        log.warning("x401 policies are not valid JSON")
        return {}
    out = {}
    for pid, pol in (entries if isinstance(entries, dict) else {}).items():
        try:
            validate_policy(pid, pol)
            out[pid] = pol
        except ValueError as exc:
            log.warning("x401 policy dropped: %s", exc)
    return out


def load_issuers(raw=None, path=None, env=None):
    """{issuer id: {"keys": [JWK, ...], "status_uri_prefixes": [...]}}.

    An entry is a single public JWK, or {"jwks": [JWK, ...], "status_uri_prefixes": [...]}.
    Anything that is not a usable public key is skipped; a key carrying a private member
    `d` is refused outright."""
    import logging
    import os
    log = logging.getLogger()
    raw = raw if raw is not None else (env if env is not None else os.environ.get("X401_TRUSTED_ISSUERS", ""))
    if not raw:
        p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "x401_issuers.json")
        try:
            with open(p, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
    try:
        doc = json.loads(raw) if raw else {}
        entries = doc.get("issuers", {}) if isinstance(doc, dict) else {}
    except ValueError:
        log.warning("x401 issuer registry is not valid JSON")
        return {}
    out = {}
    for iss, ent in (entries if isinstance(entries, dict) else {}).items():
        try:
            jwks = ent.get("jwks") if isinstance(ent, dict) and "jwks" in ent else [ent]
            keys = []
            for k in jwks:
                if not isinstance(k, dict) or "d" in k or k.get("kty") not in ("EC", "OKP", "RSA"):
                    raise ValueError("unusable key")
                if k["kty"] == "EC":
                    jose.jwk_to_p256(k)
                keys.append(k)
            if not iss or not keys:
                raise ValueError("empty")
            prefixes = ent.get("status_uri_prefixes", []) if isinstance(ent, dict) else []
            out[iss] = {"keys": keys, "status_uri_prefixes": [p for p in prefixes if isinstance(p, str) and p.startswith("https://")]}
        except Exception:
            log.warning("x401 issuer registry: skipping an unusable entry")
    return out


# =========================================================================== signer / nonce


class Signer:
    """The verifier's own identity: an ES256 key, a client_id, and a kid."""

    def __init__(self, private_jwk, client_id=DEFAULT_CLIENT_ID, kid=DEFAULT_KID):
        if private_jwk.get("kty") != "EC" or private_jwk.get("crv") != "P-256" or "d" not in private_jwk:
            raise ValueError("signer needs an EC P-256 private JWK")
        self.private_jwk, self.client_id, self.kid = private_jwk, client_id, kid
        self.public_jwk = dict(jose.public_jwk(private_jwk), kid=kid)

    def nonce_secret(self):
        import os
        explicit = os.environ.get("X401_NONCE_SECRET", "")
        if explicit:
            return jose.b64u_decode(explicit)
        return hmac.new(jose.b64u_decode(self.private_jwk["d"]), b"x401-nonce-v1", hashlib.sha256).digest()


_signer_cache = {"signer": None, "at": 0.0}
SIGNER_TTL = 300


def load_signer(env=None, fetch_secret=None, now=None):
    """The signer, or raises X401Error('verifier_not_configured').

    Source: X401_SIGNING_JWK (a JSON private JWK; for development and tests only), else the
    Secrets Manager secret named by X401_SIGNING_SECRET (default relayshield/x401_verifier_key).
    Cached for five minutes, like every other secret read in this repo, so a rotation is
    picked up without a redeploy."""
    import os
    t = now if now is not None else time.time()
    if env is None and _signer_cache["signer"] is not None and t - _signer_cache["at"] < SIGNER_TTL:
        return _signer_cache["signer"]
    environ = env if env is not None else os.environ
    client_id = environ.get("X401_CLIENT_ID", DEFAULT_CLIENT_ID)
    kid = environ.get("X401_KID", DEFAULT_KID)
    raw = environ.get("X401_SIGNING_JWK", "")
    try:
        if not raw:
            secret_id = environ.get("X401_SIGNING_SECRET", "relayshield/x401_verifier_key")
            if fetch_secret is None:
                import boto3
                fetch_secret = lambda sid: boto3.client("secretsmanager").get_secret_value(SecretId=sid)["SecretString"]  # noqa: E731
            raw = fetch_secret(secret_id)
        doc = json.loads(raw)
        jwk = doc.get("jwk", doc) if isinstance(doc, dict) else {}
        signer = Signer(jwk, client_id, kid)
    except Exception as exc:
        raise X401Error("verifier_not_configured",
                        f"x401 signing key unavailable ({type(exc).__name__})") from None
    if env is None:
        _signer_cache.update(signer=signer, at=t)
    return signer


def _route_tag(route, method):
    return jose.b64u_encode(hashlib.sha256(f"{str(method).upper()} {route}".encode()).digest()[:12])


def make_nonce(signer, policy_id, route, method, now, ttl):
    import os
    state = {"v": 1, "p": policy_id, "t": _route_tag(route, method), "i": int(now), "e": int(now) + ttl,
             "j": jose.b64u_encode(os.urandom(16))}
    body = jose.b64u_json(state)
    mac = hmac.new(signer.nonce_secret(), b"x401-nonce|" + body.encode(), hashlib.sha256).digest()
    return f"{body}.{jose.b64u_encode(mac)}"


def read_nonce(signer, nonce):
    """-> state dict, or raises X401Error('invalid_nonce'). Constant-time MAC compare."""
    try:
        body, mac = nonce.split(".")
        want = hmac.new(signer.nonce_secret(), b"x401-nonce|" + body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, jose.b64u_decode(mac)):
            raise ValueError
        state = jose.b64u_json_decode(body)
        if state.get("v") != 1 or not all(k in state for k in ("p", "t", "i", "e", "j")):
            raise ValueError
        return state
    except Exception:
        raise X401Error("invalid_nonce", "the nonce is not one this verifier issued") from None


# =========================================================================== challenge


def _client_metadata(dcql):
    fmts = {c["format"] for c in dcql["credentials"]}
    vp = {}
    if "dc+sd-jwt" in fmts:
        vp["dc+sd-jwt"] = {"sd-jwt_alg_values": list(ISSUER_ALGS[:2]), "kb-jwt_alg_values": list(ISSUER_ALGS[:2])}
    if "jwt_vc_json" in fmts:
        vp["jwt_vc_json"] = {"alg_values": list(ISSUER_ALGS[:2])}
    return {"vp_formats_supported": vp}


def create_challenge(policy_id, policies, route, method, signer, now=None):
    """-> {"payload": dict, "header": base64url, "request_id", "expires_at"}.

    Raises X401Error('unknown_policy') or ('verifier_not_configured')."""
    policy = (policies or {}).get(policy_id)
    if policy is None:
        raise X401Error("unknown_policy", "no such x401 policy")
    now = int(now if now is not None else time.time())
    ttl = policy.get("ttl_seconds", 600)
    mode = policy.get("mode", "signed")
    nonce = make_nonce(signer, policy_id, route, method, now, ttl)
    dcql = policy["dcql_query"]
    base = {"response_type": "vp_token", "response_mode": "dc_api", "nonce": nonce,
            "dcql_query": dcql, "client_metadata": _client_metadata(dcql)}
    requests = []
    if mode in ("signed", "both"):
        claims = dict(base, client_id=signer.client_id, expected_origins=list(policy["expected_origins"]),
                      iat=now, exp=now + ttl)
        jar = jose.jws_sign_es256(signer.private_jwk, {"typ": "oauth-authz-req+jwt", "kid": signer.kid}, claims)
        requests.append({"protocol": PROTOCOL_SIGNED, "data": {"request": jar}})
    if mode in ("unsigned", "both"):
        requests.append({"protocol": PROTOCOL_UNSIGNED, "data": base})
    payload = {"scheme": "x401", "version": X401_VERSION,
               "credential_requirements": {"digital": {"requests": requests}}}
    if policy.get("request_id"):
        payload["request_id"] = policy["request_id"]
    if policy.get("satisfied_requirements"):
        payload["satisfied_requirements"] = list(policy["satisfied_requirements"])
    if policy.get("payment"):
        payload["payment"] = dict(policy["payment"])
    return {"payload": payload, "header": jose.b64u_json(payload), "request_id": policy.get("request_id"),
            "expires_at": now + ttl}


def error_object(code, description="", request_id=None):
    obj = {"scheme": "x401", "version": X401_VERSION, "error": code}
    if description:
        obj["error_description"] = description[:300]
    if request_id:
        obj["request_id"] = request_id
    return obj


def error_header(code, description="", request_id=None):
    return jose.b64u_json(error_object(code, description, request_id))


# =========================================================================== DCQL


def select_claims(root, path):
    """Claims path pointer processing, OpenID4VP section 7. -> list of selected values.
    Raises ValueError where the spec says abort or return an error."""
    selected = [root]
    for comp in path:
        nxt = []
        if isinstance(comp, str):
            for el in selected:
                if not isinstance(el, dict):
                    raise ValueError("not an object")
                if comp in el:
                    nxt.append(el[comp])
        elif comp is None:
            for el in selected:
                if not isinstance(el, list):
                    raise ValueError("not an array")
                nxt.extend(el)
        elif isinstance(comp, int) and not isinstance(comp, bool) and comp >= 0:
            for el in selected:
                if not isinstance(el, list):
                    raise ValueError("not an array")
                if comp < len(el):
                    nxt.append(el[comp])
        else:
            raise ValueError("bad path component")
        selected = nxt
    if not selected:
        raise ValueError("no such claim")
    return selected


def _same(a, b):
    """Exact type-and-value match, as OpenID4VP requires: True is not 1, 1 is not 1.0."""
    return type(a) is type(b) and a == b


def claims_satisfied(root, cq):
    """Does the (verified) credential `root` satisfy this credential query's claims? Value
    restrictions are enforced here, never trusted to the wallet."""
    claims = cq.get("claims")
    if not claims:
        return True

    def ok(c):
        try:
            vals = select_claims(root, c["path"])
        except ValueError:
            return False
        want = c.get("values")
        return want is None or any(any(_same(v, w) for w in want) for v in vals)

    if cq.get("claim_sets"):
        by_id = {c.get("id"): c for c in claims}
        return any(all(ok(by_id[i]) for i in cs) for cs in cq["claim_sets"])
    return all(ok(c) for c in claims)


def disclosed_values(root, cq):
    """The requested claims, for the merchant: only what the query asked for."""
    out = {}
    for c in cq.get("claims") or []:
        try:
            vals = select_claims(root, c["path"])
        except ValueError:
            continue
        want = c.get("values")
        if want is not None:                  # return only what was asked for, not what the wallet over-shared
            vals = [v for v in vals if any(_same(v, w) for w in want)]
        out[".".join("*" if p is None else str(p) for p in c["path"])] = vals[0] if len(vals) == 1 else vals
    return out


def sets_satisfied(dcql, satisfied_ids):
    sets = dcql.get("credential_sets")
    if not sets:
        return all(cq["id"] in satisfied_ids for cq in dcql["credentials"])
    for cs in sets:
        if cs.get("required", True) and not any(all(i in satisfied_ids for i in opt) for opt in cs["options"]):
            return False
    return True


# =========================================================================== SD-JWT VC


def _sd_digest(disclosure: str) -> str:
    return jose.b64u_encode(hashlib.sha256(disclosure.encode("ascii")).digest())


def _process_sd(node, by_digest, used):
    """Replace digests with their disclosed values (SD-JWT section 7.1), strictly."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "_sd":
                continue
            out[k] = _process_sd(v, by_digest, used)
        for dig in node.get("_sd", []) or []:
            if not isinstance(dig, str):
                raise X401Error("invalid_credential", "bad _sd entry")
            d = by_digest.get(dig)
            if d is None:
                continue                             # a decoy digest: legal and ignored
            if dig in used:
                raise X401Error("invalid_credential", "a disclosure is referenced twice")
            used.add(dig)
            if len(d) != 3 or not isinstance(d[1], str):
                raise X401Error("invalid_credential", "disclosure is not an object-property disclosure")
            name = d[1]
            if name in ("_sd", "...") or name in out:
                raise X401Error("invalid_credential", "disclosed claim name collides")
            out[name] = _process_sd(d[2], by_digest, used)
        return out
    if isinstance(node, list):
        out = []
        for el in node:
            if isinstance(el, dict) and set(el.keys()) == {"..."}:
                dig = el["..."]
                d = by_digest.get(dig)
                if d is None:
                    continue
                if dig in used:
                    raise X401Error("invalid_credential", "a disclosure is referenced twice")
                used.add(dig)
                if len(d) != 2:
                    raise X401Error("invalid_credential", "disclosure is not an array-element disclosure")
                out.append(_process_sd(d[1], by_digest, used))
            else:
                out.append(_process_sd(el, by_digest, used))
        return out
    return node


def _issuer_keys(issuers, policy, iss):
    if iss not in policy["trusted_issuers"] or iss not in issuers:
        raise X401Error("untrusted_issuer", "the issuer is not trusted for this policy", issuer=str(iss)[:200])
    return issuers[iss]["keys"]


def _check_times(payload, now, what, need_exp):
    exp, nbf = payload.get("exp"), payload.get("nbf")
    for name, v in (("exp", exp), ("nbf", nbf), ("iat", payload.get("iat"))):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf"))):
            raise X401Error("invalid_credential", f"{what} {name} is not a number")
    if exp is None and need_exp:
        raise X401Error("credential_expired", f"{what} has no expiry")
    if exp is not None and now > exp + CLOCK_SKEW:
        raise X401Error("credential_expired", f"{what} has expired")
    if nbf is not None and now < nbf - CLOCK_SKEW:
        raise X401Error("credential_not_yet_valid", f"{what} is not yet valid")


def verify_sd_jwt_vc(presentation, cq, policy, issuers, nonce, audiences, issued_at, now, status_check=None):
    """-> (claims, issuer, holder_jwk). Raises X401Error."""
    if not isinstance(presentation, str) or presentation.count("~") < 1 or len(presentation) > MAX_RESULT_BYTES:
        raise X401Error("invalid_response", "not an SD-JWT presentation with key binding")
    parts = presentation.split("~")
    issuer_jwt, disclosures, kb_jwt = parts[0], parts[1:-1], parts[-1]
    if not kb_jwt:
        raise X401Error("holder_binding_failed", "no key binding JWT")
    try:
        hdr, payload_bytes, _, _ = jose.jws_parse(issuer_jwt)
        unverified = json.loads(payload_bytes.decode("utf-8"))
        claimed_iss = str(unverified.get("iss", ""))[:200] if isinstance(unverified, dict) else ""
    except Exception:
        if issuer_jwt.count(".") == 2 and issuer_jwt.endswith("."):
            raise X401Error("invalid_signature", "the credential is not signed") from None
        raise X401Error("invalid_response", "the credential is not a JWT") from None
    keys = _issuer_keys(issuers, policy, claimed_iss)
    try:
        hdr, payload = jose.jws_verify(issuer_jwt, keys, ISSUER_ALGS)
    except ValueError:
        raise X401Error("invalid_signature", "the credential signature did not verify", issuer=claimed_iss) from None
    if hdr.get("typ") not in ("dc+sd-jwt", "vc+sd-jwt"):
        raise X401Error("invalid_credential", "unexpected credential typ", issuer=claimed_iss)
    if payload.get("_sd_alg", "sha-256") != "sha-256":
        raise X401Error("invalid_credential", "unsupported _sd_alg", issuer=claimed_iss)
    _check_times(payload, now, "the credential", not policy.get("allow_credential_without_exp", False))

    cnf = payload.get("cnf")  # not selectively disclosable: it must be in the signed part
    holder_jwk = cnf.get("jwk") if isinstance(cnf, dict) else None
    if not isinstance(holder_jwk, dict) or "d" in holder_jwk:
        raise X401Error("holder_binding_failed", "the credential has no usable holder key", issuer=claimed_iss)
    try:
        kb_hdr, kb = jose.jws_verify(kb_jwt, [holder_jwk], ISSUER_ALGS, "kb+jwt")
    except ValueError:
        raise X401Error("holder_binding_failed", "the key binding signature did not verify", issuer=claimed_iss) from None
    sd_part = "~".join(parts[:-1]) + "~"
    if not hmac.compare_digest(str(kb.get("sd_hash", "")), jose.b64u_encode(hashlib.sha256(sd_part.encode("ascii")).digest())):
        raise X401Error("holder_binding_failed", "sd_hash does not cover this presentation", issuer=claimed_iss)
    _check_binding_claims(kb, nonce, audiences, issued_at, now, claimed_iss)


    by_digest = {}
    for dstr in disclosures:
        try:
            d = json.loads(jose.b64u_decode(dstr).decode("utf-8"))
        except Exception:
            raise X401Error("invalid_credential", "a disclosure is not valid", issuer=claimed_iss) from None
        if not isinstance(d, list) or len(d) not in (2, 3):
            raise X401Error("invalid_credential", "a disclosure has the wrong shape", issuer=claimed_iss)
        dig = _sd_digest(dstr)
        if dig in by_digest:
            raise X401Error("invalid_credential", "duplicate disclosure", issuer=claimed_iss)
        by_digest[dig] = d
    used = set()
    claims = _process_sd(payload, by_digest, used)
    if used != set(by_digest):
        raise X401Error("invalid_credential", "a disclosure matches nothing in the credential", issuer=claimed_iss)

    vct = claims.get("vct")
    if vct not in cq["meta"]["vct_values"]:
        raise X401Error("credential_type_mismatch", "the credential type is not one that was requested", issuer=claimed_iss)

    if status_check is not None and isinstance(claims.get("status"), dict):
        status_check(claims["status"], claimed_iss, keys, now)
    return claims, claimed_iss, holder_jwk


def _check_binding_claims(kb, nonce, audiences, issued_at, now, issuer):
    if kb.get("nonce") != nonce:
        raise X401Error("invalid_nonce", "the response is not bound to this request's nonce", issuer=issuer)
    if kb.get("aud") not in audiences:
        raise X401Error("audience_mismatch", "the response is not addressed to this verifier or origin", issuer=issuer)
    iat = kb.get("iat")
    if isinstance(iat, bool) or not isinstance(iat, (int, float)) or iat != iat:
        raise X401Error("holder_binding_failed", "the key binding has no issued-at", issuer=issuer)
    if iat > now + CLOCK_SKEW or iat < issued_at - CLOCK_SKEW:
        raise X401Error("holder_binding_failed", "the key binding was not made for this request", issuer=issuer)
    exp = kb.get("exp")
    if exp is not None and (isinstance(exp, bool) or not isinstance(exp, (int, float)) or now > exp + CLOCK_SKEW):
        raise X401Error("holder_binding_failed", "the key binding has expired", issuer=issuer)


# =========================================================================== W3C VC (JWT)


def _vc_root(payload):
    vc = payload.get("vc")
    return vc if isinstance(vc, dict) else payload


def _types_match(root_types, type_values):
    if isinstance(root_types, str):
        root_types = [root_types]
    if not isinstance(root_types, list):
        return False
    have = set(t for t in root_types if isinstance(t, str))
    for alt in type_values:
        need = {alt} if isinstance(alt, str) else set(alt) if isinstance(alt, list) else None
        if need and need <= have:
            return True
    return False


def _holder_key_for_vp(vp_header, vp_payload):
    if isinstance(vp_header.get("jwk"), dict) and "d" not in vp_header["jwk"]:
        return vp_header["jwk"]
    for did in (vp_header.get("kid"), vp_payload.get("iss")):
        if isinstance(did, str) and did.startswith(("did:key:", "did:jwk:")):
            return jose.resolve_offline_did(did.split("#", 1)[0])
    return None


def verify_jwt_vc(presentation, cq, policy, issuers, nonce, audiences, issued_at, now, status_check=None):
    """A holder-signed VP JWT carrying one or more VC JWTs. -> (claims_root, issuer, holder_jwk)."""
    if not isinstance(presentation, str) or len(presentation) > MAX_RESULT_BYTES or presentation.count(".") != 2:
        raise X401Error("invalid_response", "not a VP JWT")
    try:
        vp_header, vp_bytes, _, _ = jose.jws_parse(presentation)
        vp_unv = json.loads(vp_bytes.decode("utf-8"))
        holder_jwk = _holder_key_for_vp(vp_header, vp_unv)
        if holder_jwk is None:
            raise ValueError("no holder key")
    except Exception:
        raise X401Error("holder_binding_failed", "the holder key could not be determined") from None
    try:
        vp_header, vp = jose.jws_verify(presentation, [holder_jwk], ISSUER_ALGS)
    except ValueError:
        raise X401Error("holder_binding_failed", "the presentation signature did not verify") from None
    _check_binding_claims(vp, nonce, audiences, issued_at, now, "")
    exp = vp.get("exp")
    if exp is not None and (isinstance(exp, bool) or not isinstance(exp, (int, float)) or now > exp + CLOCK_SKEW):
        raise X401Error("holder_binding_failed", "the presentation has expired")
    vcs = (vp.get("vp") or {}).get("verifiableCredential") if isinstance(vp.get("vp"), dict) else None
    if not isinstance(vcs, list) or not vcs or len(vcs) > 5:
        raise X401Error("invalid_response", "the presentation carries no credentials")
    holder_thumb = jose.jwk_thumbprint(holder_jwk)
    first_error = None
    for vc_jwt in vcs:
        try:
            unv = jose.jws_payload(vc_jwt)
            iss = str(unv.get("iss") or (_vc_root(unv).get("issuer") if isinstance(_vc_root(unv).get("issuer"), str) else ""))[:200]
            keys = _issuer_keys(issuers, policy, iss)
            try:
                _, payload = jose.jws_verify(vc_jwt, keys, ISSUER_ALGS)
            except ValueError:
                raise X401Error("invalid_signature", "the credential signature did not verify", issuer=iss) from None
            _check_times(payload, now, "the credential", not policy.get("allow_credential_without_exp", False))
            root = _vc_root(payload)
            if not _types_match(root.get("type"), cq["meta"]["type_values"]):
                raise X401Error("credential_type_mismatch", "the credential type is not one that was requested", issuer=iss)
            cnf = payload.get("cnf") or root.get("cnf")
            bound = False
            if isinstance(cnf, dict) and isinstance(cnf.get("jwk"), dict):
                bound = jose.jwk_thumbprint(cnf["jwk"]) == holder_thumb
            subject = payload.get("sub") or (root.get("credentialSubject") or {}).get("id")
            if not bound and isinstance(subject, str) and subject.startswith(("did:key:", "did:jwk:")):
                try:
                    bound = jose.jwk_thumbprint(jose.resolve_offline_did(subject.split("#", 1)[0])) == holder_thumb
                except ValueError:
                    bound = False
            if not bound:
                raise X401Error("holder_binding_failed", "the credential is not bound to the presenting holder key", issuer=iss)
            if status_check is not None and isinstance(root.get("credentialStatus"), dict):
                raise X401Error("status_unavailable", "credentialStatus checking is not supported for jwt_vc_json", issuer=iss)
            return root, iss, holder_jwk
        except X401Error as exc:
            first_error = first_error or exc
    raise first_error


# =========================================================================== token status list


def make_status_checker(issuers, policy, fetch):
    """-> callable(status_claim, issuer, issuer_keys, now) that raises X401Error.

    `fetch(url)` -> bytes (None on failure). The URI must start with one of the issuer's
    registered `status_uri_prefixes`: a credential must not be able to point the verifier at
    an arbitrary URL. Policy `status` is "enforce" (default: no way to check = fail closed),
    or "ignore" (documented risk: a revoked credential keeps working)."""
    mode = policy.get("status", "enforce")

    def check(status, issuer, keys, now):
        sl = status.get("status_list") if isinstance(status, dict) else None
        if mode == "ignore":
            return
        if not isinstance(sl, dict) or not isinstance(sl.get("uri"), str) or isinstance(sl.get("idx"), bool) \
                or not isinstance(sl.get("idx"), int) or sl["idx"] < 0:
            raise X401Error("status_unavailable", "the credential carries a status this verifier cannot read", issuer=issuer)
        uri, idx = sl["uri"], sl["idx"]
        prefixes = (issuers.get(issuer) or {}).get("status_uri_prefixes") or []
        if not any(uri.startswith(p) for p in prefixes) or fetch is None:
            raise X401Error("status_unavailable", "the credential's status list is not one registered for this issuer", issuer=issuer)
        raw = fetch(uri)
        if not raw:
            raise X401Error("status_unavailable", "the status list could not be fetched", issuer=issuer)
        try:
            hdr, payload = jose.jws_verify(raw.decode("ascii").strip(), keys, ISSUER_ALGS, "statuslist+jwt")
            if payload.get("sub") != uri:
                raise ValueError("sub")
            exp = payload.get("exp")
            if exp is not None and now > exp + CLOCK_SKEW:
                raise ValueError("expired")
            lst = payload["status_list"]
            bits = lst["bits"]
            if bits not in (1, 2, 4, 8):
                raise ValueError("bits")
            d = zlib.decompressobj()
            data = d.decompress(jose.b64u_decode(lst["lst"]), 1_000_000)
            if d.unconsumed_tail:
                raise ValueError("too large")
            per_byte = 8 // bits
            if idx // per_byte >= len(data):
                raise ValueError("index out of range")
            value = (data[idx // per_byte] >> ((idx % per_byte) * bits)) & ((1 << bits) - 1)
        except Exception:
            raise X401Error("status_unavailable", "the status list did not verify", issuer=issuer) from None
        if value != 0:
            raise X401Error("credential_revoked", "the credential has been revoked or suspended", issuer=issuer)
    return check


# =========================================================================== result validation


def decode_artifact(header_value):
    """PROOF-RESPONSE -> Result Artifact dict. Raises X401Error('invalid_response')."""
    if not isinstance(header_value, str) or not header_value.strip() or "," in header_value:
        raise X401Error("invalid_response", "PROOF-RESPONSE must hold exactly one base64url JSON object")
    if len(header_value) > MAX_RESULT_BYTES:
        raise X401Error("invalid_response", "PROOF-RESPONSE is too large; send a credential_result_uri")
    try:
        obj = jose.b64u_json_decode(header_value)
    except Exception:
        raise X401Error("invalid_response", "PROOF-RESPONSE is not base64url JSON") from None
    return obj


def verify_result(header_value, *, policy_id, policies, issuers, route, method, signer, store,
                  now=None, agent_id=None, fetch=None):
    """Validate a PROOF-RESPONSE. -> success dict. Raises X401Error on any failure.

    `agent_id` is the caller identity ALREADY AUTHENTICATED elsewhere (for us, the TAP
    keyid); it is only consulted when the policy sets bind_agent. `store.seen(key, now)` is
    the single-use store, or None to skip single use (tests only)."""
    now = now if now is not None else time.time()
    policy = (policies or {}).get(policy_id)
    if policy is None:
        raise X401Error("unknown_policy", "no such x401 policy")
    request_id = policy.get("request_id")
    try:
        artifact = decode_artifact(header_value)
        if artifact.get("scheme") == "x401" and "access_token" in artifact:
            raise X401Error("unsupported_token", "Verification Tokens are not issued by this verifier")
        has_inline, has_ref = "credential_result" in artifact, "credential_result_uri" in artifact
        if has_inline == has_ref:
            raise X401Error("invalid_response", "exactly one of credential_result or credential_result_uri is required")
        result_uri = None
        if has_ref:
            result_uri = artifact["credential_result_uri"]
            prefixes = policy.get("result_uri_prefixes") or []
            if not (isinstance(result_uri, str) and result_uri.startswith("https://") and any(result_uri.startswith(p) for p in prefixes)):
                raise X401Error("reference_not_accepted", "this verifier only dereferences result URIs it recognises")
            raw = fetch(result_uri) if fetch else None
            if not raw or len(raw) > MAX_RESULT_BYTES:
                raise X401Error("reference_unavailable", "the credential result could not be fetched")
            try:
                result = json.loads(raw.decode("utf-8"))
            except Exception:
                raise X401Error("invalid_response", "the referenced result is not JSON") from None
        else:
            result = artifact["credential_result"]
        out = _validate_credential_result(result, policy, policy_id, issuers, route, method, signer, store,
                                          now, agent_id, artifact, request_id, fetch)
        if result_uri is not None and store is not None and store.seen("ref|" + result_uri, now):
            raise X401Error("replayed_nonce", "this result reference was already used")
        return out
    except X401Error as exc:
        exc.request_id = request_id
        raise


def _validate_credential_result(result, policy, policy_id, issuers, route, method, signer, store, now,
                                agent_id, artifact, request_id, fetch):
    if not isinstance(result, dict) or not isinstance(result.get("protocol"), str):
        raise X401Error("invalid_response", "the credential result needs a protocol")
    protocol = result["protocol"]
    mode = policy.get("mode", "signed")
    offered = {PROTOCOL_SIGNED} if mode == "signed" else {PROTOCOL_UNSIGNED} if mode == "unsigned" else {PROTOCOL_SIGNED, PROTOCOL_UNSIGNED}
    if protocol not in offered:
        raise X401Error("unsupported_protocol", "the result protocol is not one this request offered")
    data = result.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            raise X401Error("invalid_response", "the result data is not JSON") from None
    if not isinstance(data, dict):
        raise X401Error("invalid_response", "the result data must be an object")
    if "error" in data:
        raise X401Error("wallet_error", f"the wallet returned an error: {str(data['error'])[:60]}")
    if "response" in data and "vp_token" not in data:
        raise X401Error("response_encryption_unsupported", "encrypted responses are not supported by this verifier")
    vp_token = data.get("vp_token")
    dcql = policy["dcql_query"]
    queries = {cq["id"]: cq for cq in dcql["credentials"]}
    if not isinstance(vp_token, dict) or not vp_token:
        raise X401Error("invalid_response", "vp_token must be a non-empty object")
    for qid, pres in vp_token.items():
        if qid not in queries:
            raise X401Error("invalid_response", "vp_token names a credential query that was not requested")
        if not isinstance(pres, list) or not pres or (not queries[qid].get("multiple") and len(pres) != 1):
            raise X401Error("invalid_response", "vp_token holds the wrong number of presentations")

    # Find the nonce in the first presentation (UNVERIFIED), recover our state from it, and
    # only then check that EVERY presentation is bound to that same nonce.
    nonce = _peek_nonce(next(iter(vp_token.values()))[0])
    state = read_nonce(signer, nonce)
    if state["p"] != policy_id:
        raise X401Error("policy_mismatch", "the result was issued for a different policy")
    if state["t"] != _route_tag(route, method):
        raise X401Error("route_mismatch", "the result was issued for a different route")
    if now > state["e"] + CLOCK_SKEW:
        raise X401Error("expired_request", "the request has expired")

    audiences = set()
    if protocol == PROTOCOL_SIGNED:
        audiences.add(signer.client_id)
        audiences.update("origin:" + o for o in policy.get("expected_origins") or [])
    else:
        audiences.update("origin:" + o for o in policy.get("unsigned_allowed_origins") or [])

    status_check = make_status_checker(issuers, policy, fetch)
    satisfied, credentials, first_error, holder_thumbs = set(), {}, None, set()
    for qid, presentations in vp_token.items():
        cq = queries[qid]
        for pres in presentations:
            try:
                if cq["format"] == "dc+sd-jwt":
                    root, iss, hjwk = verify_sd_jwt_vc(pres, cq, policy, issuers, nonce, audiences, state["i"], now, status_check)
                else:
                    root, iss, hjwk = verify_jwt_vc(pres, cq, policy, issuers, nonce, audiences, state["i"], now, status_check)
                if not claims_satisfied(root, cq):
                    raise X401Error("claims_not_satisfied", "the credential does not satisfy the requested claims", issuer=iss)
            except X401Error as exc:
                first_error = first_error or exc          # discard this presentation (spec), keep the reason
                continue
            satisfied.add(qid)
            holder_thumbs.add(jose.jwk_thumbprint(hjwk))
            credentials.setdefault(qid, []).append({"format": cq["format"], "issuer": iss,
                                                    "claims": disclosed_values(root, cq)})
    if not sets_satisfied(dcql, satisfied):
        raise first_error or X401Error("claims_not_satisfied", "the presented credentials do not satisfy the request")
    if len(holder_thumbs) > 1:
        raise X401Error("holder_binding_failed", "the credentials were presented by different holder keys")

    if policy.get("bind_agent"):
        claimed = artifact.get("agent_id")
        if not agent_id:
            raise X401Error("agent_binding_failed", "this policy requires an authenticated agent and none was supplied")
        if claimed is not None and claimed != agent_id:
            raise X401Error("agent_binding_failed", "the Result Artifact names a different agent than the one authenticated")
    elif artifact.get("agent_id") is not None and agent_id and artifact["agent_id"] != agent_id:
        raise X401Error("agent_binding_failed", "the Result Artifact names a different agent than the one authenticated")

    # Single use is the LAST step, so a result that fails any check above never burns the nonce.
    if store is not None and store.seen("x401rp|" + state["j"], now):
        raise X401Error("replayed_nonce", "this request's nonce was already used")
    return {"ok": True, "policy": policy_id, "request_id": request_id,
            "satisfied_requirements": list(policy.get("satisfied_requirements") or []),
            "credentials": credentials, "holder_key_thumbprint": next(iter(holder_thumbs)),
            "agent_id": agent_id if policy.get("bind_agent") else None, "protocol": protocol}


def _peek_nonce(presentation):
    """The nonce claim of a presentation's binding JWT, UNVERIFIED. Used only to find our own
    HMAC-protected state; every later step re-checks the nonce against a verified token."""
    try:
        if not isinstance(presentation, str):
            raise ValueError
        if "~" in presentation:
            last = presentation.rsplit("~", 1)[1]
            if not last:
                raise X401Error("holder_binding_failed", "no key binding JWT")
            tok = last
        else:
            tok = presentation
        nonce = jose.jws_payload(tok).get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise ValueError
        return nonce
    except X401Error:
        raise
    except Exception:
        raise X401Error("invalid_response", "the presentation carries no nonce") from None
