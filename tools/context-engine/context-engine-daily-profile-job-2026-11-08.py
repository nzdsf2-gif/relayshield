#!/usr/bin/env python3
"""Context-engine item 1: daily per-tenant risk profile job (Q5).

Console-side, runs once a day (Q1). Computes one risk profile per
tenant from the TI corpus and the tenant's own history, and stores
it keyed by tenant id, so the resolved policy fetch can carry the
profile to the proxy. A new tenant's first profile contains at
least sector and risk score (Q6); the sector's kit families are
filled from the corpus on the first run, and history accumulates
after that.

What this file is:
- The computation itself (compute_profile), pure and deterministic,
  so it can be tested without any store or network.
- A run_daily_job driver that iterates tenants, computes, and stores.
- Store adapters. The storage binding is configuration, marked
  below, because the console Worker file
  (cloudflare_worker_mcpfw.js) is not on this VM.

Storage binding (CONFIGURATION, wire it on the console):
- The console Worker serves the resolved policy, and the profile
  rides inside it under the 'risk_profile' key. The Worker stores
  one profile per tenant. The intended binding is the console's
  tenant store, keyed by tenant id. This file ships a JSON-file
  store for test and a DynamoDB store (table from
  CE_PROFILE_TABLE, key tenant_id). The Worker KV binding is
  documented in ConsoleKVStore below and in the build summary; it
  is a separate wire-up on the Mac, not invented here.

Cloudflare Worker scheduled trigger (reference shape, for the
Worker file on the Mac; the Worker is JavaScript, this job is
Python, so the trigger either calls the job's HTTP endpoint or
the computation is ported into the Worker):
  export default {
    async scheduled(event, env, ctx) {
      ctx.waitUntil(runDailyProfiles(env));
    }
  };
  A cron trigger of "0 5 * * *" runs it once a day. The profile
  version increments on every successful recompute, and
  computed_at is the run time, so the proxy can judge age
  against the 7 day maximum (Q2).

Risk score (0-100, explainable, no black box):
  score = 0.50 * flag_rate_pct
        + 0.30 * (distinct kit families seen / 5, capped at 1) * 100
        + 0.20 * sector_baseline
  where flag_rate_pct is (flagged + blocked) / screened * 100 over
  the last 30 days. A new tenant has no history, so its score is
  the sector baseline, or 50.0 neutral when the sector has no
  baseline. The score is clamped to 0-100 and rounded to one
  decimal. The score is an input to the gate's lookup, not a
  verdict: it never changes a policy decision on its own.

History window: the last 30 days of screened-call audit rows for
the tenant. The history source is an adapter (see
TenantHistorySource); the real adapter reads the console's
screened-call rows. The corpus source is an adapter too
(CorpusSource); the real adapter reads relayshield_intel_iocs
and the sector kit-family table.

Usage (test, MAC TERMINAL):
  python3 context-engine-daily-profile-job-2026-11-08.py \
      --tenants-file tenants.json --history-file history.json \
      --corpus-file corpus.json --store-dir ./profiles
  Tenants, history, and corpus are JSON files in the shapes
  documented on TenantHistorySource and CorpusSource. The job
  writes one profile JSON per tenant into --store-dir and prints
  a report. No network, no Stripe, no live object.
"""

import argparse
import json
import os
import sys
import time

# The profile module lives next to this file in ~/workspace/your_files/
# under a hyphenated name, which is not a valid Python module name,
# so load it by path. When the module is installed into mcp_proxy/
# as risk_profile.py, replace this block with:
#   from .risk_profile import RiskProfile
# (or the equivalent import for the job's host) and delete the shim.
import importlib.util as _importlib_util

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROFILE_PATH = os.path.join(
    _HERE, "context-engine-risk-profile-module-2026-11-08.py")
_spec = _importlib_util.spec_from_file_location(
    "context_engine_risk_profile", _PROFILE_PATH)
_profile_mod = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_profile_mod)
RiskProfile = _profile_mod.RiskProfile
MAX_PROFILE_AGE_SECONDS = _profile_mod.MAX_PROFILE_AGE_SECONDS

HISTORY_WINDOW_DAYS = 30
MAX_HIGH_RISK_TOOLS = 20
MAX_KIT_FAMILIES = 20
MAX_KNOWN_COUNTERPARTIES = 50
NEUTRAL_RISK_SCORE = 50.0

# Sector-default high-risk tools. Configuration: extend per sector
# as the corpus shows which tools attackers abuse for that sector.
SECTOR_HIGH_RISK_TOOLS = {
    "fintech": ["transfer_funds", "exec_shell", "withdraw"],
    "crypto": ["transfer_funds", "exec_shell", "sign_transaction"],
    "ecommerce": ["refund_order", "exec_shell"],
    "saas": ["exec_shell", "delete_resource"],
}


def clamp_score(value):
    """Clamp a risk score to 0-100 and round to one decimal."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return NEUTRAL_RISK_SCORE
    return round(max(0.0, min(100.0, value)), 1)


def compute_profile(tenant, history, corpus, previous=None, now=None):
    """Compute one tenant's risk profile from history and corpus.

    tenant:  {"tenant_id": str, "sector": str,
              "known_recipients": [str, ...]} (known_recipients optional)
    history: {"screened": int, "flagged": int, "blocked": int,
              "tools_flagged": {"tool_name": count, ...},
              "kit_families_seen": ["Family", ...],
              "counterparties_clean": ["0x...", ...]}
             Counts are for the last 30 days. Any key may be absent.
    corpus:  {"sector_kit_families": {"sector": ["Family", ...]},
              "sector_baseline": {"sector": float}}
             Sector kit families come from the corpus; the baseline
             is the sector's average risk score across tenants, or
             absent when the sector has no data.
    previous: the tenant's existing RiskProfile, or None for a new
             tenant. The version increments from it.
    now:     epoch seconds; defaults to time.time().

    Returns a RiskProfile. Never raises on missing or malformed
    inputs: a tenant with no history gets the new-tenant profile
    (Q6), and a malformed input is treated as empty history.
    """
    now = now if now is not None else time.time()
    tenant = tenant if isinstance(tenant, dict) else {}
    history = history if isinstance(history, dict) else {}
    corpus = corpus if isinstance(corpus, dict) else {}
    tenant_id = str(tenant.get("tenant_id") or "")
    sector = str(tenant.get("sector") or "")
    version = (previous.version + 1) if previous is not None else 1

    screened = history.get("screened") or 0
    flagged = history.get("flagged") or 0
    blocked = history.get("blocked") or 0
    try:
        screened = int(screened)
        flagged = int(flagged)
        blocked = int(blocked)
    except (TypeError, ValueError):
        screened = flagged = blocked = 0
    screened = max(0, screened)
    flagged = max(0, flagged)
    blocked = max(0, blocked)

    sector_baselines = corpus.get("sector_baseline") or {}
    sector_baseline = sector_baselines.get(sector)
    try:
        sector_baseline = float(sector_baseline)
    except (TypeError, ValueError):
        sector_baseline = None

    if screened > 0:
        flag_rate_pct = (flagged + blocked) / screened * 100.0
        kit_families_seen = history.get("kit_families_seen") or []
        if not isinstance(kit_families_seen, list):
            kit_families_seen = []
        kit_share = min(len(set(kit_families_seen)), 5) / 5.0
        baseline = (sector_baseline if sector_baseline is not None
                    else NEUTRAL_RISK_SCORE)
        risk_score = (0.50 * flag_rate_pct
                      + 0.30 * kit_share * 100.0
                      + 0.20 * baseline)
        score_breakdown = {
            "flag_rate_pct": round(flag_rate_pct, 1),
            "flag_weight": 0.50,
            "flag_contribution": round(0.50 * flag_rate_pct, 1),
            "kit_share": round(kit_share, 2),
            "kit_weight": 0.30,
            "kit_contribution": round(0.30 * kit_share * 100.0, 1),
            "sector_baseline": round(baseline, 1),
            "baseline_weight": 0.20,
            "baseline_contribution": round(0.20 * baseline, 1),
            "screened": screened,
            "flagged": flagged,
            "blocked": blocked,
        }
    else:
        # Q6: new tenant, no history. Score is the sector baseline,
        # or neutral 50.0 when the sector has no baseline.
        risk_score = (sector_baseline if sector_baseline is not None
                      else NEUTRAL_RISK_SCORE)
        _base = sector_baseline if sector_baseline is not None else NEUTRAL_RISK_SCORE
        score_breakdown = {
            "flag_rate_pct": None,
            "flag_weight": 0.50,
            "flag_contribution": 0.0,
            "kit_share": None,
            "kit_weight": 0.30,
            "kit_contribution": 0.0,
            "sector_baseline": round(_base, 1),
            "baseline_weight": 0.20,
            "baseline_contribution": round(0.20 * _base, 1),
            "screened": 0,
            "flagged": 0,
            "blocked": 0,
            "note": "new tenant, no history; score is the sector baseline",
        }
    risk_score = clamp_score(risk_score)

    # High-risk tools: tools flagged or blocked for this tenant in
    # the window, most frequent first, plus the sector defaults.
    tools_flagged = history.get("tools_flagged") or {}
    if not isinstance(tools_flagged, dict):
        tools_flagged = {}
    ranked_tools = sorted(
        ((str(tool), count) for tool, count in tools_flagged.items()
         if isinstance(count, (int, float))),
        key=lambda item: (-item[1], item[0]))
    high_risk_tools = [tool for tool, _ in ranked_tools]
    for tool in SECTOR_HIGH_RISK_TOOLS.get(sector, []):
        if tool not in high_risk_tools:
            high_risk_tools.append(tool)
    high_risk_tools = high_risk_tools[:MAX_HIGH_RISK_TOOLS]

    # Kit families: families seen in this tenant's history, plus
    # the sector's families from the corpus. History first.
    kit_families_seen = history.get("kit_families_seen") or []
    if not isinstance(kit_families_seen, list):
        kit_families_seen = []
    kit_families = []
    for family in kit_families_seen:
        family = str(family)
        if family and family not in kit_families:
            kit_families.append(family)
    sector_families = (corpus.get("sector_kit_families") or {}).get(sector) or []
    if not isinstance(sector_families, list):
        sector_families = []
    for family in sector_families:
        family = str(family)
        if family and family not in kit_families:
            kit_families.append(family)
    kit_families = kit_families[:MAX_KIT_FAMILIES]

    # Known counterparties: counterparties with clean verdicts in
    # the window, plus the tenant's known-recipients list.
    counterparties = history.get("counterparties_clean") or []
    if not isinstance(counterparties, list):
        counterparties = []
    known = []
    for counterparty in counterparties:
        counterparty = str(counterparty)
        if counterparty and counterparty not in known:
            known.append(counterparty)
    known_recipients = tenant.get("known_recipients") or []
    if not isinstance(known_recipients, list):
        known_recipients = []
    for counterparty in known_recipients:
        counterparty = str(counterparty)
        if counterparty and counterparty not in known:
            known.append(counterparty)
    known = known[:MAX_KNOWN_COUNTERPARTIES]

    return RiskProfile(
        tenant_id=tenant_id,
        version=version,
        computed_at=now,
        sector=sector,
        risk_score=risk_score,
        high_risk_tools=high_risk_tools,
        kit_families=kit_families,
        known_counterparties=known,
        score_breakdown=score_breakdown,
    )


class TenantHistorySource:
    """Reads one tenant's last-30-day history. Adapter interface.

    history_for(tenant_id) returns a dict in the shape
    compute_profile expects, or {} when the tenant has no history.
    The real adapter reads the console's screened-call audit rows
    for the tenant. This file ships DictHistorySource for test.
    """

    def history_for(self, tenant_id):
        raise NotImplementedError


class DictHistorySource(TenantHistorySource):
    """In-memory history source, for test and local runs."""

    def __init__(self, histories):
        self._histories = histories or {}

    def history_for(self, tenant_id):
        history = self._histories.get(tenant_id) or {}
        return history if isinstance(history, dict) else {}


class CorpusSource:
    """Reads corpus-derived sector data. Adapter interface.

    sector_data() returns {"sector_kit_families": {...},
    "sector_baseline": {...}}. The real adapter reads
    relayshield_intel_iocs (kit families by sector, sighting
    counts) and the tenant population's sector baselines.
    This file ships DictCorpusSource for test.
    """

    def sector_data(self):
        raise NotImplementedError


class DictCorpusSource(CorpusSource):
    """In-memory corpus source, for test and local runs."""

    def __init__(self, data):
        self._data = data or {}

    def sector_data(self):
        return self._data if isinstance(self._data, dict) else {}


class ProfileStore:
    """Stores one profile per tenant, keyed by tenant id."""

    def list_tenants(self):
        raise NotImplementedError

    def get_profile(self, tenant_id):
        raise NotImplementedError

    def put_profile(self, tenant_id, profile_dict):
        raise NotImplementedError


class JsonFileStore(ProfileStore):
    """JSON-file store, one file per tenant. Test and local runs."""

    def __init__(self, directory):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, tenant_id):
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in str(tenant_id))
        return os.path.join(self.directory, f"{safe}.json")

    def list_tenants(self):
        tenants = []
        for name in sorted(os.listdir(self.directory)):
            if name.endswith(".json"):
                tenants.append(name[:-5])
        return tenants

    def get_profile(self, tenant_id):
        path = self._path(tenant_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return RiskProfile.from_dict(data, tenant_id=tenant_id)

    def put_profile(self, tenant_id, profile_dict):
        path = self._path(tenant_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(profile_dict, handle, indent=2, sort_keys=True)
            handle.write("\n")


class DynamoDBStore(ProfileStore):
    """DynamoDB store. CONFIGURATION: the console binding.

    Table from CE_PROFILE_TABLE (default relayshield_tenant_profiles),
    partition key tenant_id, attribute profile (the profile dict).
    Requires boto3 and AWS credentials with read/write on the table.
    The table must exist before the first run; this job never
    creates it. list_tenants scans the table, which is fine for a
    small tenant population and a once-a-day job.
    """

    def __init__(self, table_name=None):
        import boto3
        self.table_name = table_name or os.environ.get(
            "CE_PROFILE_TABLE", "relayshield_tenant_profiles")
        self.table = boto3.resource("dynamodb").Table(self.table_name)

    def list_tenants(self):
        tenants = []
        kwargs = {}
        while True:
            response = self.table.scan(
                ProjectionExpression="tenant_id", **kwargs)
            tenants.extend(item["tenant_id"]
                           for item in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return sorted(set(tenants))

    def get_profile(self, tenant_id):
        response = self.table.get_item(Key={"tenant_id": tenant_id})
        item = response.get("Item") or {}
        profile = item.get("profile")
        if not profile:
            return None
        return RiskProfile.from_dict(profile, tenant_id=tenant_id)

    def put_profile(self, tenant_id, profile_dict):
        self.table.put_item(Item={"tenant_id": tenant_id,
                                  "profile": profile_dict,
                                  "updated_at": profile_dict.get("computed_at")})


class ConsoleKVStore(ProfileStore):
    """Console Worker KV binding. NOT WIRED: see the build summary.

    The console Worker serves the resolved policy, and the profile
    rides inside it. The intended binding is the Worker's tenant
    store, keyed by tenant id, with the profile stored as JSON
    under the 'risk_profile' key of the resolved policy. The
    Worker file (cloudflare_worker_mcpfw.js) is not on this VM,
    so the KV namespace name and the policy assembly point are
    not invented here. When the Worker is available, replace this
    class with the real binding: get the profile from the tenant
    store, put it back the same way, and list tenants from the
    tenant store. Until then, this class raises on every call so
    a misconfiguration is loud, never silent.
    """

    def __init__(self, namespace=None):
        raise NotImplementedError(
            "ConsoleKVStore is not wired: the console Worker file "
            "is not on this VM. Use JsonFileStore for test or "
            "DynamoDBStore, and wire the Worker KV binding on the "
            "Mac. See the build summary.")

    def list_tenants(self):
        raise NotImplementedError

    def get_profile(self, tenant_id):
        raise NotImplementedError

    def put_profile(self, tenant_id, profile_dict):
        raise NotImplementedError


def run_daily_job(store, history_source, corpus_source, tenants,
                  now=None):
    """Run one daily profile computation pass.

    tenants: a list of {"tenant_id": str, "sector": str,
    "known_recipients": [...]} dicts. Returns a report dict:
    {"tenants": N, "written": N, "new": N, "errors": [{"tenant_id",
    "error"}]}. A failure for one tenant is recorded and the job
    continues with the rest; a failure never stops the daily run.
    """
    now = now if now is not None else time.time()
    corpus = corpus_source.sector_data()
    report = {"tenants": len(tenants), "written": 0, "new": 0,
              "errors": []}
    for tenant in tenants:
        tenant_id = str((tenant or {}).get("tenant_id") or "")
        if not tenant_id:
            report["errors"].append({"tenant_id": "",
                                     "error": "tenant record has no tenant_id"})
            continue
        try:
            previous = store.get_profile(tenant_id)
            history = history_source.history_for(tenant_id)
            profile = compute_profile(tenant, history, corpus,
                                      previous=previous, now=now)
            store.put_profile(tenant_id, profile.to_dict())
            report["written"] += 1
            if previous is None:
                report["new"] += 1
        except Exception as exc:
            report["errors"].append({"tenant_id": tenant_id,
                                     "error": str(exc)})
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Daily per-tenant risk profile job (context-engine item 1).")
    parser.add_argument("--tenants-file", required=True,
                        help="JSON file: a list of tenant records.")
    parser.add_argument("--history-file", required=True,
                        help="JSON file: {tenant_id: history dict}.")
    parser.add_argument("--corpus-file", required=True,
                        help="JSON file: {sector_kit_families, sector_baseline}.")
    parser.add_argument("--store-dir", default="",
                        help="JSON-file store directory (test/local).")
    parser.add_argument("--store", default="json",
                        choices=["json", "dynamodb"],
                        help="Store backend. dynamodb uses CE_PROFILE_TABLE.")
    args = parser.parse_args()

    with open(args.tenants_file, encoding="utf-8") as handle:
        tenants = json.load(handle)
    with open(args.history_file, encoding="utf-8") as handle:
        histories = json.load(handle)
    with open(args.corpus_file, encoding="utf-8") as handle:
        corpus = json.load(handle)
    if not isinstance(tenants, list):
        raise SystemExit("tenants file must be a JSON list")

    if args.store == "dynamodb":
        store = DynamoDBStore()
    else:
        if not args.store_dir:
            raise SystemExit("--store-dir is required for the json store")
        store = JsonFileStore(args.store_dir)

    report = run_daily_job(store, DictHistorySource(histories),
                           DictCorpusSource(corpus), tenants)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
