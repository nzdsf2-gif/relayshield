"""Explainable confidence scoring for MCP Proxy Firewall verdicts.

Every verdict carries a confidence score (0-100) plus the cause codes
that produced it, so an operator can see exactly which signals drove a
decision. The score is a noisy-OR combination of per-signal weights:
each weight is the standalone confidence that the signal alone
justifies the verdict, and corroborating signals raise the total with
diminishing returns. Nothing is a black box: the weights are
documented in CAUSE_CODES and every verdict lists its inputs, each
with its marginal contribution.

Method for BLOCK / QUARANTINE:
    confidence = 1 - product(1 - w_i) over firing signals, capped at 97.
    A single strong signal (e.g. POLICY_DENY at 95) already yields high
    confidence; each additional corroborating signal closes the
    remaining gap toward certainty.

Method for ALLOW:
    confidence = 70 + sum of clean-layer bonuses, capped at 92.
    A clean verdict never claims near-certainty: absence of detected
    signals is weaker evidence than presence. Each clean check layer
    that actually ran adds its bonus.
"""

# Cause codes. "weight" is the standalone confidence (0-100) that this
# signal alone justifies the verdict. "kind" is "threat" for
# verdict-driving signals or "clean" for clean-check layers used on
# the ALLOW path. Descriptions are shown in the dashboard and must
# stay free of em dashes.
CAUSE_CODES = {
    "POLICY_DENY": {
        "weight": 95,
        "kind": "threat",
        "description": "Policy explicitly denies this tool for this agent",
    },
    "CREDENTIAL_EXFILTRATION": {
        "weight": 90,
        "kind": "threat",
        "description": "Credential material bound for a non-identity-provider domain",
    },
    "OAUTH_TAMPERING": {
        "weight": 88,
        "kind": "threat",
        "description": "OAuth flow targets an unaffiliated domain",
    },
    "ATTACK_CHAIN": {
        "weight": 88,
        "kind": "threat",
        "description": "Multi-stage attack pattern matched (read, network, email or lateral movement)",
    },
    "KIT_MATCH": {
        "weight": 85,
        "kind": "threat",
        "description": "Scam-kit fingerprint matched in content",
    },
    "MALICIOUS_URL_HIGH": {
        "weight": 82,
        "kind": "threat",
        "description": "Threat-intel hit: high-risk URL in tool call or result",
    },
    "SECRET_LEAK": {
        "weight": 82,
        "kind": "threat",
        "description": "Private key or secret material in tool result",
    },
    "PROMPT_INJECTION": {
        "weight": 80,
        "kind": "threat",
        "description": "Known prompt-injection phrase matched in tool result",
    },
    "POLICY_APPROVAL": {
        "weight": 75,
        "kind": "threat",
        "description": "Policy requires operator approval for this tool",
    },
    "MALICIOUS_URL_MEDIUM": {
        "weight": 70,
        "kind": "threat",
        "description": "Threat-intel hit: medium-risk URL in tool call or result",
    },
    "PII_LEAK": {
        "weight": 65,
        "kind": "threat",
        "description": "Unredacted PII pattern in tool result",
    },
    "BEHAVIOR_ANOMALY": {
        "weight": 60,
        "kind": "threat",
        "risk_scaled": True,
        "description": "Behavior deviates from the agent baseline",
    },
    "SYNTHETIC_INSTRUCTION": {
        "weight": 45,
        "kind": "threat",
        "description": "Novel instruction-like phrasing, no known pattern matched",
    },
    # Clean-check layers for the ALLOW path. Each layer that actually
    # ran adds its bonus on top of the 70 base.
    "TI_SCREEN_CLEAN": {
        "weight": 6,
        "kind": "clean",
        "description": "Threat-intel screen ran: no indicators matched",
    },
    "CONTENT_SCREEN_CLEAN": {
        "weight": 6,
        "kind": "clean",
        "description": "Content screen ran: no poison patterns found",
    },
    "OAUTH_IDP_VALIDATED": {
        "weight": 8,
        "kind": "clean",
        "description": "OAuth endpoint validated against a known identity provider",
    },
    "ISOLATION_VERIFIED": {
        "weight": 5,
        "kind": "clean",
        "description": "Per-server isolation verified: neighbor verdict does not leak",
    },
    "SCREENING_UNAVAILABLE": {
        "weight": -40,
        "kind": "clean",
        "description": "TI screening unavailable; allowed fail-open, treat with caution",
    },
}

_CLEAN_BASE = 70
_CLEAN_CAP = 92
_THREAT_CAP = 97


def _signal_weight(code, risk=None):
    """Resolve the effective weight for a cause code.

    BEHAVIOR_ANOMALY scales with the behavioral risk score:
    weight = 60 + risk/100 * 25, capped at 85.
    """
    spec = CAUSE_CODES.get(code)
    if spec is None:
        return 0
    w = spec["weight"]
    if spec.get("risk_scaled") and risk is not None:
        try:
            w = min(85, 60 + float(risk) / 100.0 * 25)
        except (TypeError, ValueError):
            pass
    return w


def _noisy_or(weights):
    """Combine independent signal weights: 1 - product(1 - w)."""
    remaining = 1.0
    for w in weights:
        remaining *= 1.0 - min(max(w, 0), 100) / 100.0
    return (1.0 - remaining) * 100.0


def score_verdict(verdict, signals):
    """Score a verdict from its firing signals.

    verdict: "ALLOW" | "BLOCK" | "QUARANTINE" (case-insensitive).
    signals: list of {"code": str, "detail": str, "risk": float|None}.

    Returns {"confidence": int,
             "cause_codes": [{"code", "description", "weight",
                              "detail", "marginal_gain"}],
             "method": str}.
    marginal_gain is the percentage-point contribution of that signal
    computed leave-one-out against the other signals, so the strongest
    driver is visible at a glance.
    """
    v = str(verdict or "").upper()
    cleaned = []
    for s in signals or []:
        code = s.get("code")
        if code not in CAUSE_CODES:
            continue
        cleaned.append({
            "code": code,
            "detail": str(s.get("detail") or ""),
            "risk": s.get("risk"),
        })

    if v == "ALLOW":
        layers = [s for s in cleaned
                  if CAUSE_CODES[s["code"]]["kind"] == "clean"]
        total_bonus = sum(CAUSE_CODES[s["code"]]["weight"]
                          for s in layers)
        confidence = min(_CLEAN_CAP, _CLEAN_BASE + total_bonus)
        codes = [{
            "code": s["code"],
            "description": CAUSE_CODES[s["code"]]["description"],
            "weight": CAUSE_CODES[s["code"]]["weight"],
            "detail": s["detail"],
            "marginal_gain": CAUSE_CODES[s["code"]]["weight"],
        } for s in layers]
        if not codes:
            codes = [{
                "code": "NO_FLAGS_FOUND",
                "description": "Screened: no signals fired",
                "weight": 0,
                "detail": "",
                "marginal_gain": 0,
            }]
            confidence = _CLEAN_BASE
        return {
            "confidence": int(round(confidence)),
            "cause_codes": codes,
            "method": "clean-layers: 70 base + per-layer bonus, capped at 92",
        }

    weights = [_signal_weight(s["code"], s["risk"]) for s in cleaned]
    combined = _noisy_or(weights)
    confidence = min(_THREAT_CAP, int(round(combined)))
    codes = []
    for i, s in enumerate(cleaned):
        others = weights[:i] + weights[i + 1:]
        gain = _noisy_or(weights) - _noisy_or(others)
        codes.append({
            "code": s["code"],
            "description": CAUSE_CODES[s["code"]]["description"],
            "weight": int(round(weights[i])),
            "detail": s["detail"],
            "marginal_gain": int(round(gain)),
        })
    # Strongest driver first.
    codes.sort(key=lambda c: c["marginal_gain"], reverse=True)
    if not codes:
        codes = [{
            "code": "NO_SIGNALS",
            "description": "Verdict issued with no recorded signals",
            "weight": 0,
            "detail": "",
            "marginal_gain": 0,
        }]
        confidence = 50
    return {
        "confidence": confidence,
        "cause_codes": codes,
        "method": "noisy-or: 1 - product(1 - w_i), capped at 97",
    }


# Map screener poison categories to default cause codes, used when a
# caller does not declare explicit signals.
CATEGORY_CAUSE_CODES = {
    "prompt_injection": ["PROMPT_INJECTION"],
    "kit_match": ["KIT_MATCH"],
    "malicious_url": ["MALICIOUS_URL_HIGH"],
    "secret_leak": ["SECRET_LEAK"],
    "credential_exfiltration": ["CREDENTIAL_EXFILTRATION"],
    "oauth_tampering": ["OAUTH_TAMPERING"],
    "pii_leak": ["PII_LEAK"],
    "behavioral_anomaly": ["BEHAVIOR_ANOMALY"],
    "attack_chain": ["ATTACK_CHAIN"],
    "policy_deny": ["POLICY_DENY"],
    "policy_approval": ["POLICY_APPROVAL"],
    "unknown_synthetic": ["SYNTHETIC_INSTRUCTION"],
}


def signals_for_category(category, detail="", risk=None):
    """Default signals for a screener poison category."""
    codes = CATEGORY_CAUSE_CODES.get(category, [])
    return [{"code": c, "detail": detail, "risk": risk} for c in codes]
