"""
relayshield_weekly_metrics — Monday 8am ET weekly summary email.

Queries DynamoDB + Stripe to produce a snapshot of:
  - Subscribers (B2C WhatsApp/Telegram)
  - Monitored emails
  - B2A API keys + intel access
  - Alerts fired this week
  - Stripe metered call counts (per endpoint)
  - Stripe MRR / revenue
  - x402 PAYG calls
"""

import html
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr
import urllib.request
import urllib.parse
import base64

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb   = boto3.resource("dynamodb", region_name="us-east-1")
secrets_sm = boto3.client("secretsmanager", region_name="us-east-1")
ses        = boto3.client("ses", region_name="us-east-1")

REPORT_TO   = "nzdsf2@gmail.com"
FROM_EMAIL  = "noreply@relayshield.net"

STRIPE_SECRET_ID = "relayshield/stripe_secret_key"

METER_IDS = {
    # "Breach Checks" ID fixed 2026-07-21 — was mtr_...C6K, a typo/stale value
    # that doesn't exist in Stripe (confirmed via GET /v1/billing/meters
    # against the live account; every other ID below matched correctly).
    "Breach Checks":       "mtr_61UqU8q6nlQdMPAr041L2dcjOeFiYC3E",
    "SIM Swap Checks":     "mtr_61UqUARUHvyTlYkSl41L2dcjOeFiYJDE",
    "Infostealer Checks":  "mtr_61UqUBOxVALkTTvyg41L2dcjOeFiYCZM",
    "Domain Scans":        "mtr_61UqUCB2UrzRm7uoD41L2dcjOeFiYBGS",
    "OAuth Watchlist":     "mtr_61Ur2ihCGTkg0x0e941L2dcjOeFiYHI8",
    "Crypto Intel":        "mtr_61UrHQF3RCwXHFGYJ41L2dcjOeFiYC6K",
    # Expanded 2026-07-21 — the original 6 above were the only ones tracked,
    # but Stripe has 24 active meters (confirmed via GET /v1/billing/meters
    # against the live account); the weekly report was blind to 18 real
    # endpoints' usage. Names below match Stripe's display_name exactly.
    "Session Risk / AiTM Detection":  "mtr_61UtbhiF85sIm6F5T41L2dcjOeFiYK52",
    "Supply Chain Risk Check":        "mtr_61Utbh1k09SzkuuMG41L2dcjOeFiYTCK",
    "Identity Correlation":           "mtr_61UtxPFUiMG9Mentf41L2dcjOeFiYSue",
    "Ransomware Risk Check":          "mtr_61UtxrJi0qr6DT1xx41L2dcjOeFiYQIy",
    "NHI Exposure Check":             "mtr_61Uu9H3DWivakzzXi41L2dcjOeFiYUd6",
    "Secret Scan":                    "mtr_61Uu9Hc3wcbCK45FL41L2dcjOeFiY1Vo",
    "Target Risk Score":              "mtr_61UuClNkaAsChi7yv41L2dcjOeFiYERk",
    "Asset Intel Calls":              "mtr_61UubRUs9BHOeMnzh41L2dcjOeFiYPOq",
    "Threat Actor Calls":             "mtr_61UubRU2XPhWNdvNY41L2dcjOeFiY4bQ",
    "CVE Identity Risk Calls":        "mtr_61Uugll5Ru4r4wC1v41L2dcjOeFiYNWK",
    "Identity Risk Score Calls":      "mtr_61UugllCKpK8qcuy041L2dcjOeFiYOv2",
    "Bulk IOC Lookup":                "mtr_61Uux3cezRztroXbc41L2dcjOeFiYR1M",
    "IOC Pivot":                      "mtr_61Uux4byMu61KQ4CK41L2dcjOeFiYX9E",
    "Brand Monitor":                  "mtr_61Uux501UQPfZ092S41L2dcjOeFiY93A",
    "bulk-identity-risk":             "mtr_61Uv2aSvzUfotoAZP41L2dcjOeFiY69A",
    "Tech-stack-cve":                 "mtr_61Uvi9noj6VkjvUGV41L2dcjOeFiY5j6",
    "RelayShield MCP Registry Risk Calls":        "mtr_61V02jP3L11wXI4Bq41L2dcjOeFiYFtg",
    "RelayShield Prompt Injection Breach Calls":  "mtr_61V02jPXe6zjibjUr41L2dcjOeFiYPeq",
    # New endpoints (competitive benchmark roadmap), added 2026-07-21 —
    # brand-new Stripe Meters, created same day.
    "Cert Expiry":                    "mtr_61V52QbHnRWvqUR2P41L2dcjOeFiYSwC",
    "IP Intel":                       "mtr_61V52Qc8Tc38uCTV741L2dcjOeFiY1H6",
}


def _stripe_get(path: str, stripe_key: str) -> dict:
    url = f"https://api.stripe.com{path}"
    creds = base64.b64encode(f"{stripe_key}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _get_stripe_key() -> str:
    raw = secrets_sm.get_secret_value(SecretId=STRIPE_SECRET_ID)["SecretString"]
    try:
        return json.loads(raw).get("stripe_secret_key", raw)
    except Exception:
        return raw.strip()


def _week_ago_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()


def _scan_count(table_name: str) -> int:
    table = dynamodb.Table(table_name)
    resp  = table.scan(Select="COUNT")
    count = resp["Count"]
    while "LastEvaluatedKey" in resp:
        resp   = table.scan(Select="COUNT", ExclusiveStartKey=resp["LastEvaluatedKey"])
        count += resp["Count"]
    return count


def _new_this_week(table_name: str, date_field: str) -> int:
    cutoff = _week_ago_iso()
    table  = dynamodb.Table(table_name)
    resp   = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr(date_field).gte(cutoff),
        Select="COUNT",
    )
    count = resp["Count"]
    while "LastEvaluatedKey" in resp:
        resp   = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr(date_field).gte(cutoff),
            Select="COUNT",
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        count += resp["Count"]
    return count


AWS_MARKETPLACE_TIER_PRICES = {
    "ti_starter":   499,
    "ti_unlimited": 999,
}

def _aws_marketplace_stats() -> dict:
    """AWS Marketplace subscriber activations and revenue, monthly + YTD.
    Listing went live 2026-07-05. AWS Marketplace subscriptions don't run
    through Stripe — they're provisioned via SNS subscribe-success into
    relayshield_api_keys with source="aws_marketplace" (see
    relayshield_aws_marketplace.py). Revenue here is an ESTIMATE (active
    subscriber count × flat-rate list price per tier), not AWS's actual
    collected/disbursed revenue — that lives in AWS Marketplace's own
    billing reports (Collections and disbursements), not queryable from
    this Lambda without a separate AWS Marketplace billing API integration."""
    table = dynamodb.Table("relayshield_api_keys")
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("source").eq("aws_marketplace")
    )
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("source").eq("aws_marketplace"),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items += resp.get("Items", [])

    now         = datetime.now(timezone.utc)
    year_start  = datetime(now.year, 1, 1, tzinfo=timezone.utc).isoformat()
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()

    # Dedup by aws_customer_id, keeping each customer's earliest record.
    # Found 2026-07-13: AWS re-runs its own compliance audit against the
    # fulfillment endpoint repeatedly (subscribe/cancel loops) before a
    # listing passes review — same synthetic customer_id resubscribing
    # several times looked like several distinct "new activations" here.
    first_seen: dict = {}
    for i in items:
        cid = i.get("aws_customer_id")
        if not cid:
            continue
        created = i.get("created_at") or ""
        if cid not in first_seen or created < (first_seen[cid].get("created_at") or ""):
            first_seen[cid] = i
    distinct_customers = list(first_seen.values())

    activations_month = sum(1 for i in distinct_customers if (i.get("created_at") or "") >= month_start)
    activations_ytd    = sum(1 for i in distinct_customers if (i.get("created_at") or "") >= year_start)
    active_subscribers = [i for i in items if i.get("active")]

    # "This month" revenue = every currently-active subscriber's flat monthly
    # fee, since they're billed monthly regardless of when they joined.
    revenue_month_est = sum(AWS_MARKETPLACE_TIER_PRICES.get(i.get("aws_dimension"), 0)
                             for i in active_subscribers)

    # YTD = each active subscriber's monthly fee × months billed so far this
    # year (from whichever is later: their signup month or January).
    revenue_ytd_est = 0
    for i in active_subscribers:
        price = AWS_MARKETPLACE_TIER_PRICES.get(i.get("aws_dimension"), 0)
        try:
            created = datetime.fromisoformat((i.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            created = now
        start_month  = max(created, datetime(now.year, 1, 1, tzinfo=timezone.utc))
        months_billed = (now.year - start_month.year) * 12 + (now.month - start_month.month) + 1
        revenue_ytd_est += price * max(months_billed, 0)

    return {
        "activations_month":  activations_month,
        "activations_ytd":    activations_ytd,
        "active_total":       len(active_subscribers),
        "revenue_month_est":  revenue_month_est,
        "revenue_ytd_est":    revenue_ytd_est,
    }


# Channel attribution.
#
# This was a hardcoded list of four sources until 2026-08-09, and the counting
# expression only had buckets for those four. Every other source was silently
# DROPPED, not folded into an "other" row. Measured against the live table on
# the day it was fixed: 35 of 39 keys were invisible, including all 13 Bundle A
# keys and all 8 AWS Marketplace keys. The `hf-smolagents` row was permanently
# zero as well, because the value actually stored is `hf_smolagents_demo`.
#
# That is the worst possible failure for a report whose whole job is telling you
# which channels work: it does not look broken, it looks like the channel
# produced nothing. A new channel would have to be added here by hand or it
# would read as a dead channel forever.
#
# So sources are now derived from the data. A channel that has never been seen
# shows as absent, a channel that appears once shows immediately, and nothing
# needs editing here when the next one ships.

# Presentation only. Anything not listed still appears, using its raw value.
_SOURCE_LABELS = {
    "direct":         "Direct",
    "rsscan":         "rsscan",
    "metamask-snap":  "MetaMask Snap",
    "github":         "GitHub",
    "n8n":            "n8n",
    "tines":          "Tines",
    "langchain":      "LangChain",
    "llmjacking":     "LLMjacking post",
    "cs_mobile":      "Crypto Shield Mobile",
}


def _source_group(source: str) -> str:
    """Which section of the report a source belongs in.

    Acquisition channels are kept apart from Marketplace fulfilment and from
    demo keys on purpose. Lumping 13 Bundle A fulfilment keys in with developer
    signups would drown exactly the signal this section exists to show.
    """
    s = (source or "direct").lower()
    if s.startswith("aws_marketplace"):
        return "aws"
    if s.endswith("_demo") or s in ("demo_portal",) or "test" in s:
        return "demo"
    return "channel"


def _label(source: str) -> str:
    if source in _SOURCE_LABELS:
        return _SOURCE_LABELS[source]
    if source.startswith("aws_marketplace"):
        rest = source[len("aws_marketplace"):].strip("_")
        if not rest:
            return "Threat Intelligence (TI)"
        pending = rest.endswith("_pending")
        if pending:
            rest = rest[: -len("_pending")]
        name = rest.replace("_", " ").title()
        return f"{name} (pending)" if pending else name
    return source.replace("_", " ")


def _group_sources(counts: dict) -> dict:
    """Split a {source: value} mapping into the three report sections.

    Every input key lands in exactly one section, so the section totals always
    reconcile to the grand total. That property is what makes a silent drop
    impossible to reintroduce.
    """
    out = {"channel": {}, "aws": {}, "demo": {}}
    for src, val in counts.items():
        out[_source_group(src)][src] = val
    return {g: dict(sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))) for g, v in out.items()}


_GROUP_HEADINGS = [
    ("channel", "By channel"),
    ("aws",     "AWS Marketplace fulfilment"),
    ("demo",    "Demo and internal keys"),
]


def _hdr(text: str) -> str:
    return (f'  <tr><td colspan="2" style="padding-top:6px;color:#888;'
            f'font-size:12px">{text}</td></tr>')


def _source_rows(by_source: dict, new_by_source: dict, attributed: int, total: int) -> str:
    """Key-count rows, one per source actually present, grouped."""
    out = []
    for group, heading in _GROUP_HEADINGS:
        rows = by_source.get(group) or {}
        if not rows:
            continue
        out.append(_hdr(heading))
        for src, count in rows.items():
            new = (new_by_source.get(group) or {}).get(src, 0)
            delta = f' <span style="color:#2e9e5b">+{new} this week</span>' if new else ""
            out.append(f'  <tr><td>&nbsp;&nbsp;{_label(src)}</td>'
                       f'<td><b>{count}</b>{delta}</td></tr>')
    if attributed != total:
        out.append('  <tr><td colspan="2" style="color:#e94560;font-size:12px">'
                   f'Attribution mismatch: {attributed} of {total} keys accounted for. '
                   'A source is being dropped.</td></tr>')
    return "\n".join(out)


def _mrr_rows(mrr_by_source: dict) -> str:
    """MRR rows, one per source actually present, grouped."""
    out = []
    for group, heading in _GROUP_HEADINGS:
        rows = mrr_by_source.get(group) or {}
        rows = {k: v for k, v in rows.items() if v}
        if not rows:
            continue
        out.append(_hdr(f"MRR {heading[0].lower()}{heading[1:]}"))
        for src, amt in rows.items():
            out.append(f'  <tr><td>&nbsp;&nbsp;{_label(src)}</td><td><b>${amt}</b></td></tr>')
    if not out:
        out.append(_hdr("MRR by channel"))
        out.append('  <tr><td>&nbsp;&nbsp;No active subscriptions</td><td><b>$0.00</b></td></tr>')
    return "\n".join(out)


def _api_key_stats() -> dict:
    table = dynamodb.Table("relayshield_api_keys")
    resp  = table.scan()
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp   = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items += resp.get("Items", [])

    cutoff     = _week_ago_iso()
    total      = len(items)
    intel      = sum(1 for i in items if i.get("intel_access"))
    new_week   = sum(1 for i in items if (i.get("created_at") or "") >= cutoff)
    intel_calls= sum(int(i.get("intel_period_calls") or 0) for i in items)
    counts: dict = {}
    new_counts: dict = {}
    for i in items:
        src = (i.get("source") or "direct")
        counts[src] = counts.get(src, 0) + 1
        if (i.get("created_at") or "") >= cutoff:
            new_counts[src] = new_counts.get(src, 0) + 1
    return {
        "total":              total,
        "intel_enabled":      intel,
        "new_this_week":      new_week,
        "intel_calls_period": intel_calls,
        "by_source":          _group_sources(counts),
        # Per-channel NEW keys is the number that actually answers "is this
        # channel working". A cumulative count cannot distinguish a channel that
        # delivered once a year ago from one delivering every week.
        "new_by_source":      _group_sources(new_counts),
        # Reconciliation guard. If this ever disagrees with `total`, a source is
        # being dropped again and the report should say so rather than quietly
        # under-report.
        "attributed_total":   sum(counts.values()),
    }


def _stripe_mrr(stripe_key: str) -> dict:
    try:
        subs = []
        for status in ("active", "past_due"):
            data = _stripe_get(f"/v1/subscriptions?status={status}&limit=100&expand[]=data.latest_invoice", stripe_key)
            subs.extend(data.get("data", []))
        mrr_by_source: dict = {}
        for s in subs:
            inv = s.get("latest_invoice")
            if isinstance(inv, dict) and inv.get("total") is not None:
                amount = inv["total"] / 100
            elif s.get("plan"):
                amount = s["plan"]["amount"] / 100
            else:
                continue
            if s.get("plan", {}).get("interval") == "year":
                amount = amount / 12
            # Previously any unrecognised source was rewritten to "direct",
            # which did not lose the money but did attribute it to the wrong
            # channel. Silently crediting one channel with another's revenue is
            # worse than showing an unfamiliar label, so the real value is kept.
            source = (s.get("metadata") or {}).get("source") or "direct"
            mrr_by_source[source] = mrr_by_source.get(source, 0.0) + amount
        total_mrr = sum(mrr_by_source.values())
        return {
            "active_subscriptions": len(subs),
            "mrr_usd":              round(total_mrr, 2),
            "mrr_by_source":        _group_sources({k: round(v, 2) for k, v in mrr_by_source.items()}),
        }
    except Exception as exc:
        logger.warning("Stripe MRR fetch failed: %s", exc)
        return {"active_subscriptions": 0, "mrr_usd": 0.0,
                "mrr_by_source": {"channel": {}, "aws": {}, "demo": {}}}


# Founder's own account — used for testing checkout flows. Its invoices are
# real Stripe charges but not real customer revenue, so they're excluded from
# the revenue metric below (confirmed 2026-07-04: $59.96 of a $104.93 YTD
# total traced back to self-paid test invoices on this address).
INTERNAL_TEST_EMAILS = {"relayshieldadmin@gmail.com"}


# CS Mobile's two Stripe Payment Link prices (PaywallScreen.tsx) — confirmed
# 2026-07-05 via the Payment Links API, not guessed.
CS_MOBILE_PRICE_IDS = {
    "price_1ToLjdL2dcjOeFiYVuBGPZgI",  # monthly, $10.99
    "price_1ToLtuL2dcjOeFiYGivL2rts",  # annual, $105.99
}


def _cs_mobile_stats() -> dict:
    """Crypto Shield Mobile subscriber activations and revenue, monthly + YTD.
    In review on Solana dApp Store as of 2026-07-04 — likely near-zero real
    data until approved and live, but the tracking should already be in place
    for when it is. Subscriptions are identified by CS Mobile's specific
    Stripe price IDs, not by a generic "crypto" product name match, since
    other RelayShield products also touch crypto/wallet features."""
    try:
        stripe_key = _get_stripe_key()
        now         = datetime.now(timezone.utc)
        year_start  = int(datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp())
        month_start = int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())

        # ── Activations: count subscriptions on CS Mobile's prices, by created date ──
        activations_month, activations_ytd = 0, 0
        for price_id in CS_MOBILE_PRICE_IDS:
            starting_after = None
            while True:
                path = f"/v1/subscriptions?price={price_id}&status=all&limit=100"
                if starting_after:
                    path += f"&starting_after={starting_after}"
                data  = _stripe_get(path, stripe_key)
                items = data.get("data", [])
                for sub in items:
                    created = sub.get("created", 0)
                    if (sub.get("customer_email") or "").lower() in INTERNAL_TEST_EMAILS:
                        continue
                    if created >= year_start:
                        activations_ytd += 1
                    if created >= month_start:
                        activations_month += 1
                if not data.get("has_more") or not items:
                    break
                starting_after = items[-1]["id"]

        # ── Revenue: sum paid invoices whose line items match a CS Mobile price ──
        revenue_month_cents, revenue_ytd_cents = 0, 0
        starting_after = None
        while True:
            path = (f"/v1/invoices?status=paid&created[gte]={year_start}&limit=100"
                    f"&expand[]=data.lines")
            if starting_after:
                path += f"&starting_after={starting_after}"
            data  = _stripe_get(path, stripe_key)
            items = data.get("data", [])
            for inv in items:
                if (inv.get("customer_email") or "").lower() in INTERNAL_TEST_EMAILS:
                    continue
                lines = (inv.get("lines") or {}).get("data", [])
                if not any((l.get("price") or {}).get("id") in CS_MOBILE_PRICE_IDS for l in lines):
                    continue
                total   = inv.get("total", 0)
                created = inv.get("created", 0)
                revenue_ytd_cents += total
                if created >= month_start:
                    revenue_month_cents += total
            if not data.get("has_more") or not items:
                break
            starting_after = items[-1]["id"]

        return {
            "activations_month": activations_month,
            "activations_ytd":   activations_ytd,
            "revenue_month":     round(revenue_month_cents / 100, 2),
            "revenue_ytd":       round(revenue_ytd_cents / 100, 2),
        }
    except Exception as exc:
        logger.warning("CS Mobile stats fetch failed: %s", exc)
        return {"activations_month": 0, "activations_ytd": 0, "revenue_month": 0.0, "revenue_ytd": 0.0}


def _stripe_ytd_revenue(stripe_key: str) -> float:
    """Actual cumulative revenue collected this calendar year — distinct from
    MRR, which is a current-rate snapshot, not a running total. Sums paid
    invoice totals since Jan 1, excluding the founder's own test-account
    invoices, paginating through Stripe's 100-per-page limit."""
    try:
        year_start = int(datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc).timestamp())
        total_cents = 0
        starting_after = None
        while True:
            path = f"/v1/invoices?status=paid&created[gte]={year_start}&limit=100"
            if starting_after:
                path += f"&starting_after={starting_after}"
            data  = _stripe_get(path, stripe_key)
            items = data.get("data", [])
            total_cents += sum(
                inv.get("total", 0) for inv in items
                if (inv.get("customer_email") or "").lower() not in INTERNAL_TEST_EMAILS
            )
            if not data.get("has_more") or not items:
                break
            starting_after = items[-1]["id"]
        return round(total_cents / 100, 2)
    except Exception as exc:
        logger.warning("Stripe YTD revenue fetch failed: %s", exc)
        return 0.0


def _metered_customer_ids() -> list[str]:
    """Distinct Stripe customer IDs with an active metered API key. Required
    because Stripe's event_summaries endpoint has no account-wide aggregate —
    'customer' is a required parameter, always scoped to one customer at a
    time (confirmed against Stripe's own API docs, not guessed) — so getting
    a total means looping per customer and summing client-side."""
    table = dynamodb.Table("relayshield_api_keys")
    resp  = table.scan(FilterExpression=Attr("stripe_customer_id").exists() & Attr("active").eq(True))
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp   = table.scan(
            FilterExpression=Attr("stripe_customer_id").exists() & Attr("active").eq(True),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items += resp.get("Items", [])
    # Empty string is a real value some records have (e.g. demo_portal keys
    # with no real Stripe customer) — exclude, would 400 on Stripe's side.
    return sorted({i["stripe_customer_id"] for i in items if i.get("stripe_customer_id")})


def _stripe_meter_totals(stripe_key: str) -> dict:
    """Weekly usage total per meter, summed across all metered customers.
    Fixed 2026-07-21 — the previous version called event_summaries with no
    customer parameter at all, which Stripe rejects outright
    (parameter_missing: customer) since this endpoint is always per-customer;
    it had been failing on every single run, always silently falling back to
    'n/a'. Also dropped value_grouping_window=week, which isn't a valid enum
    value (Stripe only accepts hour or day) — summing daily buckets across
    the week range gives the same total. start_time/end_time must be aligned
    to daily boundaries when using value_grouping_window=day (confirmed via
    a real 400: "start_time ... should be aligned with daily boundaries") —
    floor to midnight UTC today, go back 7 full days, end at tomorrow
    midnight UTC so today's partial day is still included."""
    today_start  = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time     = int((today_start + timedelta(days=1)).timestamp())
    week_start   = int((today_start - timedelta(days=6)).timestamp())
    results      = {name: 0 for name in METER_IDS}
    customer_ids = _metered_customer_ids()

    if not customer_ids:
        return {name: 0 for name in METER_IDS}

    for customer_id in customer_ids:
        for name, meter_id in METER_IDS.items():
            try:
                path = (f"/v1/billing/meters/{meter_id}/event_summaries"
                        f"?customer={customer_id}&start_time={week_start}&end_time={end_time}"
                        f"&value_grouping_window=day")
                data      = _stripe_get(path, stripe_key)
                summaries = data.get("data", [])
                results[name] += sum(int(s.get("aggregated_value", 0)) for s in summaries)
            except Exception as exc:
                logger.warning("Meter fetch failed customer=%s meter=%s: %s", customer_id, name, exc)
    return results


def _x402_stats() -> dict:
    """Real x402 PAYG settlement stats. Was previously reading from
    relayshield_wallet_activity_log -- Crypto Shield's Alchemy-based
    wallet drain-detection log (TTL 1hr), completely unrelated to x402
    payments -- a bug that meant this metric always showed 0/0 no matter
    how many PAYG calls actually settled. Fixed 2026-07-12/13, alongside
    adding the settlement log itself: relayshield_api.py and
    relayshield_agentic_api.py now write a record to
    relayshield_payg_settlements on every successful settlement."""
    try:
        cutoff = _week_ago_iso()
        table  = dynamodb.Table("relayshield_payg_settlements")
        resp   = table.scan()
        items  = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp   = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp.get("Items", [])

        total_calls   = len(items)
        total_revenue = sum(float(i.get("amount_usd", 0)) for i in items)
        this_week     = [i for i in items if i.get("timestamp", "") >= cutoff]
        week_calls    = len(this_week)
        week_revenue  = sum(float(i.get("amount_usd", 0)) for i in this_week)

        by_endpoint: dict[str, dict] = {}
        for i in items:
            path = i.get("path", "unknown")
            e = by_endpoint.setdefault(path, {"calls": 0, "revenue": 0.0})
            e["calls"]   += 1
            e["revenue"] += float(i.get("amount_usd", 0))
        top_endpoints = sorted(by_endpoint.items(), key=lambda x: x[1]["revenue"], reverse=True)[:5]

        return {
            "total_calls":       total_calls,
            "calls_this_week":   week_calls,
            "total_revenue":     round(total_revenue, 2),
            "revenue_this_week": round(week_revenue, 2),
            "top_endpoints":     [
                {"path": p, "calls": v["calls"], "revenue": round(v["revenue"], 2)}
                for p, v in top_endpoints
            ],
        }
    except Exception as exc:
        logger.warning("x402 stats scan failed: %s", exc)
        return {
            "total_calls": 0, "calls_this_week": 0,
            "total_revenue": 0, "revenue_this_week": 0, "top_endpoints": [],
        }


def _hf_mcp_stats() -> dict:
    """Usage/revenue from the RelayShield Agentic Attack Surface HF Space
    (relayshield_agentic_attack_surface MCP server) specifically, as opposed
    to the same metered endpoints called directly. Callers supply their own
    API key, so this is the same billed traffic as any other metered call —
    attribution works because the HF Space tags every request it makes with
    an X-RS-Source: hf-mcp-space header, and both relayshield_api.py's
    handle_metered_request and relayshield_agentic_api.py's lambda_handler
    write a tagged row to the shared relayshield_payg_settlements table on
    successful billing when that header is present (added 2026-07-15,
    alongside the Docker SDK migration)."""
    try:
        cutoff = _week_ago_iso()
        table  = dynamodb.Table("relayshield_payg_settlements")
        resp   = table.scan(FilterExpression=Attr("source").eq("hf-mcp-space"))
        items  = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp   = table.scan(FilterExpression=Attr("source").eq("hf-mcp-space"), ExclusiveStartKey=resp["LastEvaluatedKey"])
            items += resp.get("Items", [])

        # Only rows that actually took money count as revenue. `billed` and
        # `rail` were added 2026-07-30; before that the row recorded list price
        # regardless of whether anyone paid, so a TI subscriber's unlimited call
        # and an unbilled key both showed up as revenue. The first row this ever
        # produced was the AWS Marketplace auditor (awsmpsaastest@amazon.com)
        # during the Bundle D compliance test, reported as $0.35 of "revenue".
        # Older rows have no flag and are reported as unverified, not counted.
        def _billed(i):
            return bool(i.get("billed")) if "billed" in i else None

        total_calls   = len(items)
        total_revenue = sum(float(i.get("amount_usd", 0)) for i in items if _billed(i) is True)
        this_week     = [i for i in items if i.get("timestamp", "") >= cutoff]
        week_calls    = len(this_week)
        week_revenue  = sum(float(i.get("amount_usd", 0)) for i in this_week if _billed(i) is True)
        unverified    = sum(1 for i in items if _billed(i) is None)
        by_rail: dict[str, int] = {}
        for i in items:
            by_rail[i.get("rail", "unrecorded")] = by_rail.get(i.get("rail", "unrecorded"), 0) + 1

        by_endpoint: dict[str, dict] = {}
        for i in items:
            path = i.get("path", "unknown")
            e = by_endpoint.setdefault(path, {"calls": 0, "revenue": 0.0})
            e["calls"]   += 1
            if _billed(i) is True:
                e["revenue"] += float(i.get("amount_usd", 0))
        top_endpoints = sorted(by_endpoint.items(), key=lambda x: x[1]["revenue"], reverse=True)

        return {
            "total_calls":       total_calls,
            "calls_this_week":   week_calls,
            "total_revenue":     round(total_revenue, 2),
            "revenue_this_week": round(week_revenue, 2),
            "unverified_rows":   unverified,
            "by_rail":           by_rail,
            "by_endpoint":       [
                {"path": p, "calls": v["calls"], "revenue": round(v["revenue"], 2)}
                for p, v in top_endpoints
            ],
        }
    except Exception as exc:
        logger.warning("HF MCP stats scan failed: %s", exc)
        return {
            "total_calls": 0, "calls_this_week": 0,
            "total_revenue": 0, "revenue_this_week": 0, "by_endpoint": [],
            "unverified_rows": 0, "by_rail": {},
        }


def _discord_install_stats() -> dict:
    """Discord bot install footprint: servers, reach, and the App Directory gap.

    Added 2026-08-13. Until the harvester existed we could not answer "how many
    servers is the bot in", which meant no way to tell whether a post to a big
    server produced installs, and no way to track progress toward the 75-server
    Discord App Directory threshold.

    This REFRESHES rather than reading the table blind. `sync()` calls Discord,
    reconciles the table and returns live counts, so the number in the Monday
    email is true as of the moment the email was built. Reading the table alone
    would report whatever the last successful run happened to find, which could
    be weeks old and would look identical to a current number. That is the same
    stale-looks-fresh failure the freshness contract exists to prevent.

    On any failure it returns degraded=True rather than zeros. Zero servers and
    "we could not ask Discord" are very different facts, and a report that
    renders them identically is worse than one that admits the gap.
    """
    try:
        import relayshield_discord_installs as installs
    except Exception as exc:
        logger.warning("discord installs module unavailable: %s", exc)
        return {"degraded": True, "reason": "module not packaged with this Lambda"}

    try:
        stats = installs.sync(dry_run=False)
    except Exception as exc:
        logger.warning("discord install sync raised: %s", exc)
        return {"degraded": True, "reason": type(exc).__name__}

    if stats.get("error"):
        return {"degraded": True, "reason": stats["error"]}

    # Departures are the signal worth surfacing loudest: an admin removing the
    # bot is the most informative feedback this channel produces, and it is the
    # thing nobody would otherwise notice.
    return {
        "degraded":         False,
        "servers":          stats["servers"],
        "new_installs":     stats["new_installs"],
        "departures":       stats["departures"],
        "total_reach":      stats["total_reach"],
        "to_app_directory": stats["to_app_directory"],
    }


def _discord_html(d: dict) -> str:
    if d.get("degraded"):
        return (f"""<tr><td colspan="2" style="color:#e94560;"><b>Could not read Discord</b><br>
        <span style="font-size:12px;">{d.get('reason','unknown')}. This is not a report of zero
        servers; it is a report that we could not ask.</span></td></tr>""")

    rows = f"""  <tr><td>Servers with the bot</td><td><b>{d['servers']}</b></td></tr>
  <tr><td>New installs this week</td><td><b>{d['new_installs']}</b></td></tr>
  <tr><td>Combined member reach</td><td><b>{d['total_reach']:,}</b></td></tr>
  <tr><td>Servers still needed for the App Directory</td><td><b>{d['to_app_directory']}</b></td></tr>"""

    if d["departures"]:
        names = ", ".join(x["guild_name"] or x["guild_id"] for x in d["departures"])
        rows += (f"""\n  <tr><td style="color:#e94560;">Removed the bot</td>"""
                 f"""<td style="color:#e94560;"><b>{len(d['departures'])}</b> ({names})</td></tr>""")
    return rows


def _feedback_sentiment_stats() -> dict:
    """Crypto Shield Mobile in-app thumbs up/down feedback, aggregated across
    all devices in relayshield_push_tokens. One record per device (latest
    submission only) — not a running log, so this is current standing
    sentiment, not weekly delta. Positive comments are surfaced as candidate
    quotes for the site's testimonials section — still require manual review
    before publishing, this just saves hunting through DynamoDB for them."""
    try:
        table = dynamodb.Table("relayshield_push_tokens")
        resp  = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("feedback_rating").exists(),
        )
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp  = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("feedback_rating").exists(),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
            )
            items += resp.get("Items", [])

        up   = [i for i in items if i.get("feedback_rating") == "up"]
        down = [i for i in items if i.get("feedback_rating") == "down"]
        total = len(up) + len(down)
        pct_positive = round(100 * len(up) / total, 1) if total else None

        testimonial_candidates = [
            i.get("feedback_comment") for i in up if (i.get("feedback_comment") or "").strip()
        ][:10]

        return {
            "total":                total,
            "up":                   len(up),
            "down":                 len(down),
            "pct_positive":         pct_positive,
            "testimonial_candidates": testimonial_candidates,
        }
    except Exception as exc:
        logger.warning("Feedback sentiment scan failed: %s", exc)
        return {"total": 0, "up": 0, "down": 0, "pct_positive": None, "testimonial_candidates": []}


def _build_email(metrics: dict) -> str:
    week_end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s = metrics
    return f"""
<html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
<h2 style="color: #1a1a2e;">RelayShield Weekly Metrics — {week_end}</h2>

<h3 style="color: #e94560;">B2C Subscribers</h3>
<table border="0" cellpadding="4">
  <tr><td>Total users</td><td><b>{s['users_total']}</b></td></tr>
  <tr><td>New this week</td><td><b>{s['users_new']}</b></td></tr>
  <tr><td>Monitored emails</td><td><b>{s['monitored_emails']}</b></td></tr>
  <tr><td>New monitored emails (week)</td><td><b>{s['monitored_emails_new']}</b></td></tr>
</table>

<h3 style="color: #e94560;">B2A API Keys</h3>
<table border="0" cellpadding="4">
  <tr><td>Total API keys</td><td><b>{s['api_keys']['total']}</b></td></tr>
  <tr><td>New this week</td><td><b>{s['api_keys']['new_this_week']}</b></td></tr>
  <tr><td>Intel-enabled keys</td><td><b>{s['api_keys']['intel_enabled']}</b></td></tr>
  <tr><td>Intel API calls (current period)</td><td><b>{s['api_keys']['intel_calls_period']}</b></td></tr>
  {_source_rows(s['api_keys']['by_source'], s['api_keys']['new_by_source'], s['api_keys']['attributed_total'], s['api_keys']['total'])}
</table>

<h3 style="color: #e94560;">Stripe Metered Calls (Last 7 Days)</h3>
<table border="0" cellpadding="4">
{"".join(f"  <tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in s['meter_calls'].items())}
</table>

<h3 style="color: #e94560;">Discord Bot Installs</h3>
<table border="0" cellpadding="4">
{_discord_html(s['discord'])}
</table>

<h3 style="color: #e94560;">Alerts Fired</h3>
<table border="0" cellpadding="4">
  <tr><td>Breach alerts (total)</td><td><b>{s['breach_alerts_total']}</b></td></tr>
  <tr><td>Breach alerts (this week)</td><td><b>{s['breach_alerts_new']}</b></td></tr>
  <tr><td>SIM swap alerts (total)</td><td><b>{s['sim_alerts_total']}</b></td></tr>
  <tr><td>SIM swap alerts (this week)</td><td><b>{s['sim_alerts_new']}</b></td></tr>
  <tr><td>Intel alerts (total)</td><td><b>{s['intel_alerts_total']}</b></td></tr>
  <tr><td>Intel alerts (this week)</td><td><b>{s['intel_alerts_new']}</b></td></tr>
  <tr><td>TI feed IOCs (total)</td><td><b>{s['ioc_total']:,}</b></td></tr>
  <tr><td>Stolen session records</td><td><b>{s['stolen_sessions']:,}</b></td></tr>
  <tr><td>Identity graph correlations</td><td><b>{s['identity_graph']:,}</b></td></tr>
  <tr><td>Ransomware victim records</td><td><b>{s['ransomware_victims']:,}</b></td></tr>
</table>

<h3 style="color: #e94560;">Revenue</h3>
<table border="0" cellpadding="4">
  <tr><td>Active subscriptions</td><td><b>{s['stripe']['active_subscriptions']}</b></td></tr>
  <tr><td>MRR</td><td><b>${s['stripe']['mrr_usd']}</b></td></tr>
  <tr><td>Cumulative revenue (YTD)</td><td><b>${s['ytd_revenue']}</b></td></tr>
  {_mrr_rows(s['stripe']['mrr_by_source'])}
</table>

<h3 style="color: #e94560;">x402 PAYG Calls & Revenue</h3>
<table border="0" cellpadding="4">
  <tr><td>Total calls</td><td><b>{s['x402']['total_calls']}</b></td></tr>
  <tr><td>Calls this week</td><td><b>{s['x402']['calls_this_week']}</b></td></tr>
  <tr><td>Total revenue</td><td><b>${s['x402']['total_revenue']}</b></td></tr>
  <tr><td>Revenue this week</td><td><b>${s['x402']['revenue_this_week']}</b></td></tr>
  <tr><td colspan="2" style="padding-top:6px;color:#888;font-size:12px">Top endpoints by revenue</td></tr>
  {"".join(f"<tr><td>&nbsp;&nbsp;{e['path']}</td><td><b>${e['revenue']}</b> ({e['calls']} calls)</td></tr>" for e in s['x402']['top_endpoints']) or '<tr><td colspan="2" style="color:#888">No settlements yet</td></tr>'}
</table>

<h3 style="color: #e94560;">HF MCP Server — Calls & Revenue</h3>
<table border="0" cellpadding="4">
  <tr><td>Total calls</td><td><b>{s['hf_mcp']['total_calls']}</b></td></tr>
  <tr><td>Calls this week</td><td><b>{s['hf_mcp']['calls_this_week']}</b></td></tr>
  <tr><td>Total revenue</td><td><b>${s['hf_mcp']['total_revenue']}</b></td></tr>
  <tr><td>Revenue this week</td><td><b>${s['hf_mcp']['revenue_this_week']}</b></td></tr>
  <tr><td colspan="2" style="padding-top:6px;color:#888;font-size:12px">By tool</td></tr>
  {"".join(f"<tr><td>&nbsp;&nbsp;{e['path']}</td><td><b>${e['revenue']}</b> ({e['calls']} calls)</td></tr>" for e in s['hf_mcp']['by_endpoint']) or '<tr><td colspan="2" style="color:#888">No calls yet</td></tr>'}
</table>
<p style="color: #888; font-size: 11px;">Calls to RelayShield's 4 metered endpoints made via the relayshield-agentic-attack-surface HF Space (callers supply their own API key) — tagged and counted separately from direct API calls.</p>

<h3 style="color: #e94560;">AWS Marketplace — Activations & Revenue (est.)</h3>
<table border="0" cellpadding="4">
  <tr><td>New subscriber activations (this month)</td><td><b>{s['aws_marketplace']['activations_month']}</b></td></tr>
  <tr><td>New subscriber activations (YTD)</td><td><b>{s['aws_marketplace']['activations_ytd']}</b></td></tr>
  <tr><td>Active subscribers (total)</td><td><b>{s['aws_marketplace']['active_total']}</b></td></tr>
  <tr><td>Revenue (this month, estimated)</td><td><b>${s['aws_marketplace']['revenue_month_est']}</b></td></tr>
  <tr><td>Revenue (YTD, estimated)</td><td><b>${s['aws_marketplace']['revenue_ytd_est']}</b></td></tr>
</table>
<p style="color: #888; font-size: 11px;">Estimated from active-subscriber count × flat-rate list price per tier — not AWS's actual collected/disbursed revenue (see AWS Marketplace Management Portal → Billed revenue for exact figures).</p>

<h3 style="color: #e94560;">Crypto Shield Mobile — Activations & Revenue</h3>
<table border="0" cellpadding="4">
  <tr><td>New subscriber activations (this month)</td><td><b>{s['cs_mobile_stats']['activations_month']}</b></td></tr>
  <tr><td>New subscriber activations (YTD)</td><td><b>{s['cs_mobile_stats']['activations_ytd']}</b></td></tr>
  <tr><td>Revenue (this month)</td><td><b>${s['cs_mobile_stats']['revenue_month']}</b></td></tr>
  <tr><td>Revenue (YTD)</td><td><b>${s['cs_mobile_stats']['revenue_ytd']}</b></td></tr>
</table>

<h3 style="color: #e94560;">Crypto Shield Mobile Feedback</h3>
<table border="0" cellpadding="4">
  <tr><td>Devices with feedback</td><td><b>{s['cs_mobile_feedback']['total']}</b></td></tr>
  <tr><td>Positive</td><td><b>{"n/a — no feedback yet" if s['cs_mobile_feedback']['pct_positive'] is None else f"{s['cs_mobile_feedback']['pct_positive']}% ({s['cs_mobile_feedback']['up']} up / {s['cs_mobile_feedback']['down']} down)"}</b></td></tr>
</table>
{f'''<p style="color: #888; font-size: 12px; margin-top:10px;">Testimonial candidates (from thumbs-up, needs manual review before publishing):</p>
<ul style="font-size: 13px;">{"".join(f"<li>{html.escape(c)}</li>" for c in s['cs_mobile_feedback']['testimonial_candidates'])}</ul>''' if s['cs_mobile_feedback']['testimonial_candidates'] else ''}

{_lambda_health_html(s['lambda_health'])}

<p style="color: #888; font-size: 12px;">Generated by RelayShield weekly metrics Lambda</p>
</body></html>
"""


def _scheduled_lambda_health() -> dict:
    """Weekly health roll-up for every EventBridge-scheduled Lambda.

    Added 2026-07-30. relayshield-intel-monitor died at import on 2026-07-28
    (a deploy dropped a sibling module) and ran dead for two days across eight
    scheduled runs. Nothing reported it: a Lambda that fails at import emits no
    application logs, and only 3 of 30 scheduled functions had a CloudWatch
    alarm. It was noticed because the founder saw no morning output.

    Deliberately a digest rather than 27 more alarms. Per-function alarms on a
    fleet this size produce alert fatigue, and an alert nobody reads is not a
    control. This piggybacks on an email that already gets opened weekly.

    Two failure shapes are reported, because they look different in metrics:
      - errors  : the function ran and threw (the intel-monitor case)
      - silent  : the schedule is enabled but produced zero invocations, which
                  means the trigger itself is broken or the rule was detached
    """
    cw     = boto3.client("cloudwatch", region_name="us-east-1")
    events = boto3.client("events", region_name="us-east-1")

    scheduled: dict[str, str] = {}
    try:
        paginator = events.get_paginator("list_rules")
        for page in paginator.paginate():
            for rule in page.get("Rules", []):
                if rule.get("State") != "ENABLED" or not rule.get("ScheduleExpression"):
                    continue
                for tgt in events.list_targets_by_rule(Rule=rule["Name"]).get("Targets", []):
                    arn = tgt.get("Arn", "")
                    if arn.startswith("arn:aws:lambda"):
                        scheduled[arn.rsplit(":", 1)[-1]] = rule["ScheduleExpression"]
    except Exception as exc:
        logger.exception("Lambda health: could not enumerate schedules: %s", exc)
        return {"error": str(exc), "errored": [], "silent": [], "total": 0}

    end    = datetime.now(timezone.utc)
    start  = end - timedelta(days=7)
    recent = end - timedelta(days=2)
    errored, silent = [], []

    for fn, schedule in sorted(scheduled.items()):
        try:
            # 7-day totals PLUS a 48h window. Reporting only the weekly sum
            # cannot tell a resolved incident from a live outage: on 2026-07-30
            # this flagged relayshield-intel-feed as "17 of 23 failing" when the
            # errors were all from 7/23-7/24 and it had been clean for five days.
            # A digest that cries wolf about fixed problems gets ignored, which
            # is the failure mode the digest exists to prevent.
            #
            # Two calls, not one: GetMetricData applies a single StartTime and
            # EndTime to every query in the request, so per-query time ranges
            # are silently invalid and blow up the whole call.
            def _sums(win_start):
                r = cw.get_metric_data(
                    MetricDataQueries=[
                        {"Id": "e", "MetricStat": {
                            "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Errors",
                                       "Dimensions": [{"Name": "FunctionName", "Value": fn}]},
                            "Period": 604800, "Stat": "Sum"}},
                        {"Id": "i", "MetricStat": {
                            "Metric": {"Namespace": "AWS/Lambda", "MetricName": "Invocations",
                                       "Dimensions": [{"Name": "FunctionName", "Value": fn}]},
                            "Period": 604800, "Stat": "Sum"}},
                    ],
                    StartTime=win_start, EndTime=end,
                )
                v = {x["Id"]: (sum(x["Values"]) if x.get("Values") else 0) for x in r["MetricDataResults"]}
                return int(v.get("e", 0)), int(v.get("i", 0))

            errs, invs     = _sums(start)
            errs48, invs48 = _sums(recent)
        except Exception as exc:
            logger.warning("Lambda health: metric fetch failed for %s: %s", fn, exc)
            continue

        if errs:
            errored.append({"fn": fn, "errors": errs, "invocations": invs, "schedule": schedule,
                            "errors_48h": errs48, "invocations_48h": invs48,
                            # Still failing right now, as opposed to failed earlier
                            # in the week and since recovered.
                            "active": errs48 > 0,
                            "all_failed": invs48 > 0 and errs48 >= invs48})
        elif invs == 0:
            # A monthly or 30-day schedule legitimately shows zero in a 7-day
            # window, so those are not flagged as silent.
            if not any(t in schedule for t in ("30 days", "rate(30", "1 * ?", "? * ")):
                silent.append({"fn": fn, "schedule": schedule})

    errored.sort(key=lambda r: (not r["active"], not r["all_failed"], -r["errors_48h"], -r["errors"]))
    return {"errored": errored, "silent": silent, "total": len(scheduled)}


def _lambda_health_html(h: dict) -> str:
    if h.get("error"):
        return ('<h3 style="color: #e94560;">Scheduled Lambda health</h3>'
                f'<p style="color:#e94560;">Could not read health data: {html.escape(h["error"])}</p>')

    rows = ""
    for r in h["errored"]:
        if not r.get("active"):
            label  = f"recovered ({r['errors']} earlier this week)"
            colour = "#2a9d5c"
            runs   = f"{r['invocations_48h']} clean run(s) in 48h"
        elif r["all_failed"]:
            label, colour = "ALL RUNS FAILED", "#e94560"
            runs = f"{r['errors_48h']}/{r['invocations_48h']} failed in 48h"
        else:
            label, colour = f"{r['errors_48h']} error(s) in 48h", "#d98324"
            runs = f"{r['invocations_48h']} run(s) in 48h"
        rows += (f'<tr><td><code>{html.escape(r["fn"])}</code></td>'
                 f'<td style="color:{colour};"><b>{label}</b></td>'
                 f'<td>{runs}</td>'
                 f'<td style="color:#888;">{html.escape(r["schedule"])}</td></tr>')
    for r in h["silent"]:
        rows += (f'<tr><td><code>{html.escape(r["fn"])}</code></td>'
                 f'<td style="color:#e94560;"><b>NO INVOCATIONS</b></td>'
                 f'<td>0 run(s)</td>'
                 f'<td style="color:#888;">{html.escape(r["schedule"])}</td></tr>')

    if not rows:
        return ('<h3 style="color: #e94560;">Scheduled Lambda health</h3>'
                f'<p style="color:#2a9d5c;"><b>All clear.</b> {h["total"]} scheduled functions, '
                'no errors and no silent schedules in the last 7 days.</p>')

    return ('<h3 style="color: #e94560;">Scheduled Lambda health</h3>'
            f'<p><b>{len(h["errored"]) + len(h["silent"])} of {h["total"]}</b> scheduled functions '
            'need attention in the last 7 days.</p>'
            '<table border="0" cellpadding="4">'
            '<tr style="color:#888;"><td>Function</td><td>Status</td><td>Runs</td><td>Schedule</td></tr>'
            f'{rows}</table>'
            '<p style="color: #888; font-size: 11px;">ALL RUNS FAILED usually means a broken deploy '
            '(a missing module fails at import, so there are no application logs). NO INVOCATIONS '
            'means the schedule fired nothing, so the trigger itself is the problem.</p>')


def lambda_handler(event, context):
    # Health-only mode, added 2026-07-30. The fleet health digest wants a DAILY
    # cadence -- a weekly one would have taken up to 7 days to surface the
    # intel-monitor outage, and that ran 2 days before a human noticed. But the
    # full metrics email carries Stripe MRR, subscriber counts and revenue,
    # which nobody wants daily. So the same Lambda serves two schedules: a daily
    # health-only email, and the existing Monday full report which still
    # includes the health section inline.
    if (event or {}).get("mode") == "health_only":
        logger.info("Daily Lambda health digest starting")
        health = _scheduled_lambda_health()
        problems = len(health.get("errored", [])) + len(health.get("silent", []))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subject = (f"RelayShield Lambda health - {problems} need attention - {today}"
                   if problems else f"RelayShield Lambda health - all clear - {today}")
        body = f"""<html><body style="font-family: -apple-system, sans-serif;">
<h2 style="color: #1a1a2e;">RelayShield Lambda Health - {today}</h2>
{_lambda_health_html(health)}
<p style="color: #888; font-size: 12px;">Daily digest. The full metrics report still runs Mondays
and includes this same section.</p>
</body></html>"""
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [REPORT_TO]},
            Message={"Subject": {"Data": subject},
                     "Body": {"Html": {"Data": body}}},
        )
        logger.info("Daily health digest sent: %d problems across %d scheduled functions",
                    problems, health.get("total", 0))
        return {"ok": True, "mode": "health_only", "problems": problems, "health": health}

    logger.info("Weekly metrics report starting")

    stripe_key = _get_stripe_key()

    metrics = {
        "users_total":          _scan_count("relayshield_users"),
        "users_new":            _new_this_week("relayshield_users", "created_at"),
        "monitored_emails":     _scan_count("relayshield_monitored_emails"),
        "monitored_emails_new": _new_this_week("relayshield_monitored_emails", "created_at"),
        "api_keys":             _api_key_stats(),
        "discord":              _discord_install_stats(),
        "breach_alerts_total":  _scan_count("relayshield_breach_alerts"),
        "breach_alerts_new":    _new_this_week("relayshield_breach_alerts", "alert_sent_at"),
        "sim_alerts_total":     _scan_count("relayshield_sim_swap_alerts"),
        "sim_alerts_new":       _new_this_week("relayshield_sim_swap_alerts", "detected_at"),
        "intel_alerts_total":   _scan_count("relayshield_intel_alerts"),
        "intel_alerts_new":     _new_this_week("relayshield_intel_alerts", "created_at"),
        "ioc_total":            _scan_count("relayshield_intel_iocs"),
        "lambda_health":        _scheduled_lambda_health(),
        "stolen_sessions":      _scan_count("relayshield_stolen_sessions"),
        "identity_graph":       _scan_count("relayshield_identity_graph"),
        "ransomware_victims":   _scan_count("relayshield_intel_ransomware"),
        "meter_calls":          _stripe_meter_totals(stripe_key),
        "stripe":               _stripe_mrr(stripe_key),
        "ytd_revenue":          _stripe_ytd_revenue(stripe_key),
        "cs_mobile_stats":      _cs_mobile_stats(),
        "aws_marketplace":      _aws_marketplace_stats(),
        "x402":                 _x402_stats(),
        "hf_mcp":               _hf_mcp_stats(),
        "cs_mobile_feedback":   _feedback_sentiment_stats(),
    }

    html = _build_email(metrics)
    week_end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [REPORT_TO]},
        Message={
            "Subject": {"Data": f"RelayShield Weekly Metrics — {week_end}"},
            "Body":    {"Html": {"Data": html}},
        },
    )

    logger.info("Weekly metrics email sent to %s", REPORT_TO)
    return {"ok": True, "metrics": metrics}
