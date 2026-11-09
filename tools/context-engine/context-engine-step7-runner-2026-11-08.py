#!/usr/bin/env python3
"""Context-engine Step 7: daily profile job runner (KV wiring).

Runs the daily per-tenant risk profile job (Q5) and writes the
profiles to the console CONFIG_KV, where the Step 6 Worker patch
reads them for the resolved-policy response (key
"risk_profile:{tenantId}").

What it does:
- Reads the tenant list from CONFIG_KV (key "tenants" is a JSON
  list of {tenant_id, sector, known_recipients}) or from a
  --tenants-file. If neither is available, it reads the tenant
  keys directly from CONFIG_KV (keys starting "tenant:").
- Reads the corpus sector kit families from DynamoDB table
  relayshield_intel_iocs (distinct kit families per sector is
  derived from the sector_kit_families map you supply via
  --corpus-file; the live DynamoDB read is a follow-up that needs
  the sector mapping, which lives in the console config).
- Reads history from a JSON file (--history-file) in the shape the
  daily job expects, or treats history as empty (new-tenant
  baseline) when no file is given. The AUDIT_KV history adapter
  (reading screened-call rows from the console audit KV) is a
  follow-up; it needs the audit row key format confirmed on the
  Mac, and it is not invented here.
- Computes one profile per tenant with the daily job module and
  writes each profile JSON to CONFIG_KV via the Cloudflare API.

Configuration (environment):
  CLOUDFLARE_API_TOKEN : API token with KV write on the account.
    (The fleet shell exports this; do not paste the token into
    chat. The runner reads it from the environment only.)
  CLOUDFLARE_ACCOUNT_ID : Cloudflare account id.
  CE_CONFIG_KV_ID : CONFIG_KV namespace id.
    Default is the console CONFIG_KV from the wrangler deploy:
    d73105bd6b1449caa8a31abcaaaa209b
  CE_PROFILE_TABLE : DynamoDB table for the corpus (default
    relayshield_intel_iocs). Only used if --corpus-dynamodb is set.
  AWS_PROFILE : AWS CLI profile for the real account (default
    "relayshield"). The job never creates the table.

Scheduling: run once a day. The reference cron is "0 5 * * *"
(05:00 UTC). A GitHub Actions workflow for this schedule is in
context-engine-step7-daily-workflow-2026-11-08.yml, delivered
alongside this runner. Or run it from any cron that can set the
environment above.

Usage (MAC TERMINAL, from the console repo or anywhere with the
daily job module and this runner in the same directory):
  CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" \\
  CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID" \\
  python3 context-engine-step7-runner-2026-11-08.py \\
      --tenants-file tenants.json \\
      --corpus-file corpus.json \\
      --history-file history.json
  Omit --history-file to treat every tenant as new (sector
  baseline + sector kit families). Omit --tenants-file to list
  tenants from CONFIG_KV. Omit --corpus-file to use an empty
  corpus (sector baselines default to 50.0 neutral).

Exit code 0 when every tenant's profile is written. The report
prints written, new, and errors per tenant. A single tenant's
failure never stops the run.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# Load the daily job module by path (same directory).
_HERE = os.path.dirname(os.path.abspath(__file__))
_JOB_PATH = os.path.join(_HERE, "context-engine-daily-profile-job-2026-11-08.py")
import importlib.util as _importlib_util
_spec = _importlib_util.spec_from_file_location("context_engine_daily_job", _JOB_PATH)
_job = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_job)

DEFAULT_CONFIG_KV_ID = "d73105bd6b1449caa8a31abcaaaa209b"
KV_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareKVStore:
    """Writes profiles to a Cloudflare KV namespace via the API."""

    def __init__(self, account_id, api_token, namespace_id):
        self.account_id = account_id
        self.api_token = api_token
        self.namespace_id = namespace_id

    def _request(self, method, path, body=None, content_type=None):
        url = f"{KV_API_BASE}/accounts/{self.account_id}{path}"
        data = body.encode("utf-8") if isinstance(body, str) else body
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_token}")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Cloudflare API {method} {path} failed ({exc.code}): {detail}")

    def put_profile(self, tenant_id, profile_dict):
        key = f"risk_profile:{tenant_id}"
        path = f"/storage/kv/namespaces/{self.namespace_id}/values/{key}"
        payload = json.dumps(profile_dict)
        result = self._request("PUT", path, body=payload, content_type="application/json")
        if not result.get("success"):
            raise RuntimeError(f"KV put failed for {key}: {result}")
        return True

    def list_tenant_keys(self):
        path = f"/storage/kv/namespaces/{self.namespace_id}/keys?prefix=tenant:"
        result = self._request("GET", path)
        if not result.get("success"):
            raise RuntimeError(f"KV list failed: {result}")
        return [e["name"] for e in result.get("result", [])]

    def get_json(self, key):
        path = f"/storage/kv/namespaces/{self.namespace_id}/values/{key}"
        url = f"{KV_API_BASE}/accounts/{self.account_id}{path}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self.api_token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Cloudflare API GET {key} failed ({exc.code}): {detail}")


def load_json_file(path):
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenants-file", default=None)
    parser.add_argument("--history-file", default=None)
    parser.add_argument("--corpus-file", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute profiles but do not write them to KV.")
    args = parser.parse_args()

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    namespace_id = os.environ.get("CE_CONFIG_KV_ID") or DEFAULT_CONFIG_KV_ID
    if not account_id or not api_token:
        print("ABORT: CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set in the environment.")
        sys.exit(1)

    kv = CloudflareKVStore(account_id, api_token, namespace_id)

    # Tenants.
    if args.tenants_file:
        tenants = load_json_file(args.tenants_file)
    else:
        keys = kv.list_tenant_keys()
        tenants = []
        for key in keys:
            tenant = kv.get_json(key)
            if not tenant:
                continue
            tenants.append({
                "tenant_id": tenant.get("id") or key.replace("tenant:", ""),
                "sector": tenant.get("sector") or "unknown",
                "known_recipients": tenant.get("known_recipients") or [],
            })
    if not tenants:
        print("No tenants found. Nothing to do.")
        return

    # Corpus.
    corpus = {"sector_kit_families": {}, "sector_baseline": {}}
    if args.corpus_file:
        corpus = load_json_file(args.corpus_file)

    # History (empty when no file is given; new-tenant baseline).
    history_by_tenant = {}
    if args.history_file:
        history_by_tenant = load_json_file(args.history_file)

    now = int(__import__("time").time())
    written = 0
    new_count = 0
    errors = []
    for tenant in tenants:
        tenant_id = tenant["tenant_id"]
        history = history_by_tenant.get(tenant_id, {})
        try:
            # In dry-run mode, skip the KV read (no network) and
            # treat every profile as new (version 1).
            existing = None
            if not args.dry_run:
                existing = kv.get_json(f"risk_profile:{tenant_id}")
            previous = None
            if existing:
                previous = _job.RiskProfile.from_dict(existing)
            profile = _job.compute_profile(tenant, history, corpus,
                                           previous=previous, now=now)
            if not args.dry_run:
                kv.put_profile(tenant_id, profile.to_dict())
            written += 1
            if previous is None:
                new_count += 1
        except Exception as exc:
            errors.append({"tenant_id": tenant_id, "error": str(exc)})

    print(f"Profiles written: {written}, new: {new_count}, errors: {len(errors)}")
    for err in errors:
        print(f"  ERROR {err['tenant_id']}: {err['error']}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
