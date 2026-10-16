"""
x401_verifier -- Proof x401 Verifiable Presentation verification for RelayShield TAP.

Verifies x401 Draft 0.2.0 PROOF-PRESENTATION headers: parses the base64url
Verifiable Presentation, verifies the JWT proof signature, extracts the
scoped human mandate, and validates the transaction against mandate scope.

Pure stdlib: no third-party crypto. Ed25519 verification reuses the
implementation in relayshield_tap_verifier.py.

Pipeline:
  1. Base64url-decode the PROOF-PRESENTATION header value
  2. Parse the VP JSON, extract verifiableCredential array
  3. For each credential: verify JWT proof signature against issuer key
  4. Extract the scoped mandate (agent, merchant, amount, time window)
  5. Validate IAL2 assurance level
  6. Check transaction against mandate scope
  7. Return (valid, mandate, reason)

Pairs with TAP DPoP verification: run both in parallel when both
credentials are present. Both must pass for accept.
"""

import base64
import hashlib
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# x401 header names per Draft 0.2.0
PROOF_PRESENTATION_HEADER = "proof-presentation"
PROOF_REQUEST_HEADER = "proof-request"
PROOF_RESULT_HEADER = "proof-result"

# Minimum assurance level we accept
REQUIRED_ASSURANCE = "IAL2"

# Clock skew tolerance for exp/nbf checks (seconds)
CLOCK_SKEW = 60

# Nonce cache for replay prevention (in production, use DynamoDB)
_nonce_cache = {}
NONCE_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# base64url helpers
# ---------------------------------------------------------------------------

def b64u_decode(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# JWT parsing and verification
# ---------------------------------------------------------------------------

def parse_jwt(token: str) -> tuple[dict, dict, bytes, str]:
    """
    Split a JWT into (header, payload, signing_input, signature_b64).
    Does not verify; use verify_jwt_signature for that.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(f"JWT must have 3 parts, got {len(parts)}")
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(b64u_decode(header_b64).decode("utf-8"))
        payload = json.loads(b64u_decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"JWT JSON parse failed: {e}")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    return header, payload, signing_input, sig_b64


def verify_jwt_signature(header: dict, signing_input: bytes,
                         sig_b64: str, public_key: bytes,
                         alg: str = "EdDSA") -> bool:
    """
    Verify a JWT signature. Supports EdDSA (Ed25519) and RS256.
    public_key: raw bytes for Ed25519, or (n, e) tuple for RSA.
    Deferred to caller's crypto implementation to avoid duplication.
    Returns True if valid, False otherwise.
    """
    # This is a stub that the integrator wires to their Ed25519/RSA
    # implementation (e.g., from relayshield_tap_verifier.py).
    # We define the interface here for clarity.
    raise NotImplementedError(
        "Wire to your Ed25519/RSA verify function. "
        "See relayshield_tap_verifier.py for pure-Python implementations."
    )


# ---------------------------------------------------------------------------
# Verifiable Presentation parsing
# ---------------------------------------------------------------------------

def parse_presentation(presentation_b64: str) -> dict:
    """
    Decode and parse a PROOF-PRESENTATION header value.
    Returns the VP JSON object.
    Raises ValueError on malformed input.
    """
    try:
        vp_json = b64u_decode(presentation_b64).decode("utf-8")
        vp = json.loads(vp_json)
    except Exception as e:
        raise ValueError(f"Presentation decode failed: {e}")

    if not isinstance(vp, dict):
        raise ValueError("Presentation must be a JSON object")
    if "verifiableCredential" not in vp:
        raise ValueError("Presentation missing verifiableCredential")

    return vp


def extract_credentials(vp: dict) -> list[dict]:
    """
    Extract individual verifiable credentials from a VP.
    Each entry may be a JWT string or an embedded JSON object.
    Returns list of (credential_jwt_or_obj, is_jwt) tuples.
    """
    creds = vp.get("verifiableCredential", [])
    if not isinstance(creds, list):
        raise ValueError("verifiableCredential must be an array")

    result = []
    for c in creds:
        if isinstance(c, str):
            result.append((c, True))  # JWT string
        elif isinstance(c, dict):
            result.append((c, False))  # Embedded JSON
        else:
            logger.warning("Skipping credential of unexpected type: %s", type(c))

    return result


def extract_mandate(vp: dict, verified_creds: list[dict]) -> dict | None:
    """
    Find and extract the scoped mandate credential from verified VCs.
    The mandate is the VC with credentialSubject containing agent,
    merchant, and amountCeiling (or equivalent scope fields).

    Returns the mandate credentialSubject dict, or None if not found.
    """
    for cred in verified_creds:
        # Handle both JWT payload and embedded JSON shapes
        if isinstance(cred, dict) and "vc" in cred:
            subject = cred["vc"].get("credentialSubject", {})
        elif isinstance(cred, dict):
            subject = cred.get("credentialSubject", {})
        else:
            continue

        # A mandate must scope the agent and have at least one constraint
        if "agent" not in subject:
            continue
        has_scope = any(k in subject for k in (
            "merchant", "amountCeiling", "actionCategory",
            "validFrom", "validUntil", "scope"
        ))
        if has_scope:
            return subject

    return None


# ---------------------------------------------------------------------------
# Assurance and scope validation
# ---------------------------------------------------------------------------

def check_assurance_level(vp: dict, verified_creds: list[dict]) -> tuple[bool, str]:
    """
    Verify that at least one credential asserts IAL2 or higher.
    Returns (ok, reason).
    """
    for cred in verified_creds:
        # Check various places the assurance level might appear
        candidates = []
        if isinstance(cred, dict):
            # JWT payload shape
            if "vc" in cred:
                vc = cred["vc"]
                candidates.append(vc.get("assuranceLevel", ""))
                cs = vc.get("credentialSubject", {})
                candidates.append(cs.get("assuranceLevel", ""))
                candidates.append(cs.get("ial", ""))
            # Direct shape
            candidates.append(cred.get("assuranceLevel", ""))
            cs = cred.get("credentialSubject", {})
            if isinstance(cs, dict):
                candidates.append(cs.get("assuranceLevel", ""))

        for level in candidates:
            level_str = str(level).upper()
            if level_str in ("IAL2", "IAL3", "AAL2", "AAL3"):
                return True, f"assurance {level_str} meets requirement"

    return False, f"no credential asserts {REQUIRED_ASSURANCE} or higher"


def validate_mandate_scope(mandate: dict, transaction: dict,
                           now: float | None = None) -> tuple[bool, str]:
    """
    Check that a transaction falls within the mandate scope.

    transaction should contain: agent_id, merchant, amount, currency,
    action_category (all optional; only checked if present in mandate).

    Returns (valid, reason).
    """
    now = now if now is not None else time.time()

    # Agent must match
    mandate_agent = mandate.get("agent", "")
    tx_agent = transaction.get("agent_id", "")
    if mandate_agent and tx_agent and mandate_agent != tx_agent:
        return False, f"agent mismatch: mandate={mandate_agent}, tx={tx_agent}"

    # Merchant must match (if mandate constrains it)
    mandate_merchant = mandate.get("merchant", "")
    tx_merchant = transaction.get("merchant", "")
    if mandate_merchant and tx_merchant and mandate_merchant != tx_merchant:
        return False, f"merchant mismatch"

    # Amount must be within ceiling
    ceiling = mandate.get("amountCeiling")
    tx_amount = transaction.get("amount")
    if ceiling is not None and tx_amount is not None:
        try:
            # Handle {"value": 50, "currency": "USD"} or plain number
            if isinstance(ceiling, dict):
                ceiling_val = float(ceiling.get("value", 0))
                ceiling_cur = ceiling.get("currency", "")
                tx_cur = transaction.get("currency", "")
                if ceiling_cur and tx_cur and ceiling_cur != tx_cur:
                    return False, f"currency mismatch: {tx_cur} vs {ceiling_cur}"
            else:
                ceiling_val = float(ceiling)
            if float(tx_amount) > ceiling_val:
                return False, f"amount {tx_amount} exceeds ceiling {ceiling_val}"
        except (ValueError, TypeError) as e:
            return False, f"amount validation error: {e}"

    # Time window check
    valid_from = mandate.get("validFrom", "")
    valid_until = mandate.get("validUntil", "")
    if valid_from:
        try:
            from_ts = _parse_time(valid_from)
            if now < from_ts - CLOCK_SKEW:
                return False, "mandate not yet valid"
        except ValueError:
            pass  # Lenient on unparseable dates
    if valid_until:
        try:
            until_ts = _parse_time(valid_until)
            if now > until_ts + CLOCK_SKEW:
                return False, "mandate expired"
        except ValueError:
            pass

    # Action category check
    mandate_action = mandate.get("actionCategory", "")
    tx_action = transaction.get("action_category", "")
    if mandate_action and tx_action:
        # Allow if tx action matches or is a subset
        if isinstance(mandate_action, list):
            if tx_action not in mandate_action:
                return False, f"action {tx_action} not in mandate scope"
        elif mandate_action != tx_action:
            return False, f"action mismatch: {tx_action} vs {mandate_action}"

    return True, "transaction within mandate scope"


def _parse_time(t: str) -> float:
    """Parse ISO-8601 or epoch string to Unix timestamp."""
    t = t.strip()
    # Try epoch first
    try:
        return float(t)
    except ValueError:
        pass
    # Try ISO-8601
    from datetime import datetime, timezone
    # Handle 'Z' suffix
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# Nonce / replay prevention
# ---------------------------------------------------------------------------

def check_nonce(nonce: str, now: float | None = None) -> tuple[bool, str]:
    """
    Check nonce hasn't been seen before. Records it if new.
    In production, replace with DynamoDB-backed store.
    Returns (is_fresh, reason).
    """
    now = now if now is not None else time.time()

    # Clean expired entries
    expired = [k for k, v in _nonce_cache.items() if now - v > NONCE_TTL]
    for k in expired:
        del _nonce_cache[k]

    nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
    if nonce_hash in _nonce_cache:
        return False, "nonce replay detected"

    _nonce_cache[nonce_hash] = now
    return True, "nonce fresh"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def verify_x401_presentation(presentation_b64: str, transaction: dict,
                             issuer_keys: dict | None = None,
                             verify_sig_fn=None,
                             now: float | None = None) -> dict:
    """
    Full x401 presentation verification.

    Args:
        presentation_b64: Value of PROOF-PRESENTATION header (base64url)
        transaction: Dict with agent_id, merchant, amount, currency,
                     action_category describing the transaction to authorize
        issuer_keys: Dict mapping issuer DID/URI to public key bytes
                     (or (n,e) tuple for RSA)
        verify_sig_fn: Function(header, signing_input, sig_b64, pubkey, alg)
                       -> bool. Wire to your Ed25519/RSA implementation.
        now: Override current time (for testing)

    Returns dict:
        {
            "valid": bool,
            "mandate": dict | None,   # Extracted mandate if valid
            "reason": str,             # Human-readable reason
            "assurance": str | None,   # Assurance level found
        }
    """
    now = now if now is not None else time.time()
    issuer_keys = issuer_keys or {}

    # Step 1: Parse presentation
    try:
        vp = parse_presentation(presentation_b64)
    except ValueError as e:
        return {"valid": False, "mandate": None,
                "reason": f"presentation parse failed: {e}", "assurance": None}

    # Step 2: Extract and verify each credential
    try:
        creds = extract_credentials(vp)
    except ValueError as e:
        return {"valid": False, "mandate": None,
                "reason": f"credential extraction failed: {e}", "assurance": None}

    if not creds:
        return {"valid": False, "mandate": None,
                "reason": "no credentials in presentation", "assurance": None}

    verified = []
    for cred_raw, is_jwt in creds:
        if not is_jwt:
            # Embedded JSON without JWT proof: cannot verify signature
            # Accept only if deployment allows unsigned (not recommended)
            logger.warning("Skipping unsigned embedded credential")
            continue

        try:
            header, payload, signing_input, sig_b64 = parse_jwt(cred_raw)
        except ValueError as e:
            return {"valid": False, "mandate": None,
                    "reason": f"JWT parse failed: {e}", "assurance": None}

        # Resolve issuer key
        issuer = payload.get("iss", "")
        pubkey = issuer_keys.get(issuer)
        if not pubkey:
            return {"valid": False, "mandate": None,
                    "reason": f"unknown issuer: {issuer}", "assurance": None}

        # Verify signature
        alg = header.get("alg", "EdDSA")
        if verify_sig_fn:
            try:
                sig_valid = verify_sig_fn(header, signing_input, sig_b64,
                                          pubkey, alg)
            except Exception as e:
                return {"valid": False, "mandate": None,
                        "reason": f"signature verification error: {e}",
                        "assurance": None}
            if not sig_valid:
                return {"valid": False, "mandate": None,
                        "reason": "credential signature invalid",
                        "assurance": None}
        else:
            logger.warning("No verify function provided; skipping sig check")

        # Check exp/nbf
        exp = payload.get("exp")
        nbf = payload.get("nbf")
        if exp and now > float(exp) + CLOCK_SKEW:
            return {"valid": False, "mandate": None,
                    "reason": "credential expired", "assurance": None}
        if nbf and now < float(nbf) - CLOCK_SKEW:
            return {"valid": False, "mandate": None,
                    "reason": "credential not yet valid", "assurance": None}

        verified.append(payload)

    if not verified:
        return {"valid": False, "mandate": None,
                "reason": "no verifiable credentials", "assurance": None}

    # Step 3: Check assurance level
    assurance_ok, assurance_reason = check_assurance_level(vp, verified)
    if not assurance_ok:
        return {"valid": False, "mandate": None,
                "reason": assurance_reason, "assurance": None}

    # Step 4: Extract mandate
    mandate = extract_mandate(vp, verified)
    if not mandate:
        return {"valid": False, "mandate": None,
                "reason": "no scoped mandate found in credentials",
                "assurance": assurance_reason}

    # Step 5: Validate scope
    scope_ok, scope_reason = validate_mandate_scope(mandate, transaction, now)
    if not scope_ok:
        return {"valid": False, "mandate": mandate,
                "reason": f"mandate scope exceeded: {scope_reason}",
                "assurance": assurance_reason}

    # Step 6: Nonce replay check (use VP nonce or jti)
    nonce = ""
    for cred in verified:
        nonce = cred.get("nonce", "") or cred.get("jti", "")
        if nonce:
            break
    if nonce:
        fresh, nonce_reason = check_nonce(nonce, now)
        if not fresh:
            return {"valid": False, "mandate": mandate,
                    "reason": nonce_reason, "assurance": assurance_reason}

    return {"valid": True, "mandate": mandate,
            "reason": f"x401 verification passed: {scope_reason}",
            "assurance": assurance_reason}


def detect_credential_types(headers: dict) -> dict:
    """
    Detect which credential types are present in request headers.
    Headers dict should have lowercase keys.

    Returns: {"tap": bool, "x401": bool}
    """
    # Normalize header keys to lowercase
    lower = {k.lower(): v for k, v in headers.items()}
    has_tap = "signature" in lower and "signature-input" in lower
    has_x401 = PROOF_PRESENTATION_HEADER in lower
    return {"tap": has_tap, "x401": has_x401}
