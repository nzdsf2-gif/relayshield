"""Per-tenant risk profile, context-engine item 1.

A risk profile is pre-computed console-side from the TI corpus and
the tenant's own history, and delivered to the proxy inside the
resolved policy on the existing policy fetch path. The per-call gate
consults the profile (a lookup) instead of freshly computing what is
high-risk for this tenant. The profile informs the call-time check;
it does not replace it, because a decision made before the call
cannot see the arguments of the call that is about to happen.

Profile contents, per Andrew's decisions 2026-11-08:
- tenant sector and risk score (Q4, Q6: at minimum, and a new
  tenant's first profile contains at least these two).
- high-risk tools for this tenant.
- kit families relevant to the tenant's sector.
- known counterparties for this tenant.
- version and computed timestamp, so the proxy can judge age.

Decisions this module encodes:
- Q1 refresh cadence: daily (the console job recomputes daily).
- Q2 maximum profile age: 7 days (604800 seconds). Older than that
  the profile counts as stale.
- Q3 fallback: when the profile is stale or missing, the gate falls
  back to full per-call evaluation without the profile. If full
  per-call evaluation is itself unavailable, the gate fails closed
  and refuses the call, under the proxy's existing fail-closed
  posture. The fallback is logged in the audit record.
- Q6 new tenant: first profile contains at least sector and risk
  score; high-risk tools, kit families, and known counterparties
  start empty until history accumulates (kit families for the
  sector are filled by the console job from the corpus).

This module is pure logic: no I/O, no network, no storage. It runs
identically on the proxy and in the console job. It does not change
Policy 1 or Policy 2, and it does not change any gate decision: the
consultation outcome is recorded in the audit trail and attached as
evidence on flagged verdicts. Using the outcome to change a gate
decision is a follow-up decision, not in this build.
"""

import time

# Q2: maximum profile age, 7 days, in seconds.
MAX_PROFILE_AGE_SECONDS = 7 * 24 * 3600

# Freshness states, shown per tenant in the console UI.
FRESHNESS_CURRENT = "current"
FRESHNESS_STALE = "stale"
FRESHNESS_MISSING = "missing"


class RiskProfile:
    """One tenant's pre-computed risk profile.

    All fields are plain JSON values so the profile travels inside
    the resolved policy dict and stores in the console keyed by
    tenant id. No corpus internals and no other tenant's data are
    ever in a profile.
    """

    def __init__(self, tenant_id="", version=1, computed_at=0.0,
                 sector="", risk_score=0.0, high_risk_tools=None,
                 kit_families=None, known_counterparties=None,
                 score_breakdown=None):
        self.tenant_id = tenant_id or ""
        self.version = int(version) if version is not None else 1
        try:
            self.computed_at = float(computed_at or 0.0)
        except (TypeError, ValueError):
            self.computed_at = 0.0
        self.sector = sector or ""
        try:
            self.risk_score = float(risk_score or 0.0)
        except (TypeError, ValueError):
            self.risk_score = 0.0
        self.high_risk_tools = list(high_risk_tools or [])
        self.kit_families = list(kit_families or [])
        self.known_counterparties = list(known_counterparties or [])
        self.score_breakdown = dict(score_breakdown) if isinstance(score_breakdown, dict) else {}

    @classmethod
    def from_dict(cls, data, tenant_id=""):
        """Build a profile from a dict, tolerating missing fields.

        Returns None when data is not a dict or is empty, so a
        missing profile is distinguishable from an empty one.
        """
        if not isinstance(data, dict) or not data:
            return None
        return cls(
            tenant_id=data.get("tenant_id") or tenant_id or "",
            version=data.get("version", 1),
            computed_at=data.get("computed_at", 0.0),
            sector=data.get("sector", ""),
            risk_score=data.get("risk_score", 0.0),
            high_risk_tools=data.get("high_risk_tools"),
            kit_families=data.get("kit_families"),
            known_counterparties=data.get("known_counterparties"),
            score_breakdown=data.get("score_breakdown"),
        )

    @classmethod
    def default_for_new_tenant(cls, tenant_id="", sector="",
                               risk_score=0.0, now=None):
        """Q6: a new tenant's first profile.

        Contains at least sector and risk score. High-risk tools,
        kit families, and known counterparties start empty until
        history accumulates; the console job fills the sector's kit
        families from the corpus on the first daily run.
        """
        return cls(
            tenant_id=tenant_id or "",
            version=1,
            computed_at=now if now is not None else time.time(),
            sector=sector or "",
            risk_score=risk_score,
            high_risk_tools=[],
            kit_families=[],
            known_counterparties=[],
        )

    def to_dict(self):
        """Plain dict, safe to store and to send in the policy."""
        return {
            "tenant_id": self.tenant_id,
            "version": self.version,
            "computed_at": self.computed_at,
            "sector": self.sector,
            "risk_score": self.risk_score,
            "high_risk_tools": list(self.high_risk_tools),
            "kit_families": list(self.kit_families),
            "known_counterparties": list(self.known_counterparties),
            "score_breakdown": dict(self.score_breakdown),
        }

    def age_seconds(self, now=None):
        """Seconds since the profile was computed."""
        now = time.time() if now is None else now
        return max(0.0, now - self.computed_at)

    def is_stale(self, max_age_seconds=MAX_PROFILE_AGE_SECONDS, now=None):
        """True when the profile is older than the maximum age (Q2)."""
        return self.age_seconds(now) > max_age_seconds

    def freshness(self, max_age_seconds=MAX_PROFILE_AGE_SECONDS, now=None):
        """FRESHNESS_CURRENT or FRESHNESS_STALE. Never 'missing' here:
        a missing profile is None, not a RiskProfile, so callers use
        freshness_of() for the three-state answer."""
        if self.is_stale(max_age_seconds, now):
            return FRESHNESS_STALE
        return FRESHNESS_CURRENT


def freshness_of(profile, max_age_seconds=MAX_PROFILE_AGE_SECONDS,
                 now=None):
    """Three-state freshness for a profile that may be None.

    Returns FRESHNESS_MISSING when there is no profile, FRESHNESS_STALE
    when it is older than the maximum age, else FRESHNESS_CURRENT.
    """
    if profile is None:
        return FRESHNESS_MISSING
    return profile.freshness(max_age_seconds, now)


def resolve_profile(policy, tenant_id=""):
    """Pull the risk profile out of a resolved policy dict.

    The console delivers the profile inside the resolved policy as
    the 'risk_profile' key. Returns a RiskProfile, or None when the
    policy carries no profile. Never raises on a malformed profile:
    a malformed profile is treated as missing, and the gate falls
    back to full per-call evaluation.
    """
    if not isinstance(policy, dict):
        return None
    raw = policy.get("risk_profile")
    if not raw:
        return None
    # Per-tenant isolation: a profile that names a different tenant
    # than the one requested is never applied. The policy fetch is
    # keyed by tenant and location, so this should not happen; when
    # it does, fail closed to full per-call evaluation rather than
    # consulting another tenant's profile.
    if isinstance(raw, dict):
        raw_tenant = raw.get("tenant_id")
        if raw_tenant and tenant_id and raw_tenant != tenant_id:
            return None
    try:
        return RiskProfile.from_dict(raw, tenant_id=tenant_id)
    except Exception:
        return None


def consult_profile(profile, tool_name, arguments=None,
                    max_age_seconds=MAX_PROFILE_AGE_SECONDS, now=None):
    """Consult a profile for one tools/call. This is the gate lookup.

    Returns a dict with:
    - profile_version: the profile version consulted, 0 when none.
    - profile_freshness: current, stale, or missing.
    - profile_fallback: True when the profile is stale or missing
      and the gate must fall back to full per-call evaluation (Q3).
      False when the profile was current and consulted.
    - tool_high_risk: True when the called tool is in the profile's
      high-risk tools list. False otherwise, including when the
      profile is stale or missing (a missing profile is never
      treated as 'no risk'; the fallback flag says so).
    - counterparty_known: True when the call's counterparty is in
      the profile's known counterparties, False when the call has
      a counterparty that is not known, None when the call carries
      no counterparty to check.
    - relevant_kit_families: the profile's kit families for this
      tenant's sector, empty when the profile is stale or missing.

    The lookup never changes a gate decision in this build. It
    records what the profile says so the audit trail and any flagged
    verdict can show it. Using tool_high_risk to change a decision
    is a follow-up decision, not in this build.
    """
    now = time.time() if now is None else now
    freshness = freshness_of(profile, max_age_seconds, now)
    if profile is None or freshness != FRESHNESS_CURRENT:
        return {
            "profile_version": profile.version if profile is not None else 0,
            "profile_freshness": freshness,
            "profile_fallback": True,
            "tool_high_risk": False,
            "counterparty_known": None,
            "relevant_kit_families": [],
        }
    tool = tool_name or ""
    high_risk = tool in (profile.high_risk_tools or [])
    counterparty = None
    if isinstance(arguments, dict):
        counterparty = (
            arguments.get("counterparty")
            or arguments.get("recipient")
            or arguments.get("to")
            or arguments.get("wallet")
            or arguments.get("address")
        )
    if counterparty is None or counterparty == "":
        counterparty_known = None
    else:
        counterparty_known = str(counterparty) in (
            profile.known_counterparties or [])
    return {
        "profile_version": profile.version,
        "profile_freshness": FRESHNESS_CURRENT,
        "profile_fallback": False,
        "tool_high_risk": bool(high_risk),
        "counterparty_known": counterparty_known,
        "relevant_kit_families": list(profile.kit_families or []),
    }
