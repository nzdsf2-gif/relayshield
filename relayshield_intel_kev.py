"""
RelayShield INTEL-FEED-4 — CISA Known Exploited Vulnerabilities (KEV) Ingestion

Polls the free CISA KEV catalog daily and writes actively-exploited CVEs to
relayshield_intel_cve. Entries flagged knownRansomwareCampaignUse=True are
also written to relayshield_intel_iocs (ioc_type=cve) so they surface through
the existing /v1/intel/telegram query surface alongside Telegram/ThreatFox/
URLhaus IOCs.

Honest correlation note (per Andrew, June 16 2026): KEV data is vendor/product
based ("Apache HTTP Server", "Ivanti Connect Secure"), but RelayShield does not
currently collect a per-customer software/tech-stack inventory — only emails,
phones, domains, and wallets are monitored. True per-user correlation (e.g.
"your monitored domain runs the vulnerable product") is NOT implemented here
because the underlying data doesn't exist yet. What this Lambda DOES feed into
the correlation engine: ransomware-flagged KEV entries are recorded as a
*global* signal type (kev_ransomware_active) that the breach monitor's
ATTACK_CHAINS can combine with a user's existing breach/SIM-swap signals to
raise severity during an active ransomware exploitation window — see
relayshield_breach_monitor.py CORRELATION_WINDOW_HOURS / ATTACK_CHAINS. Per-
product targeting requires a future onboarding field (customer-declared tech
stack) — tracked as a follow-up, not built in this pass.

Sources:
  CISA KEV: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
  EPSS:     https://api.first.org/data/v1/epss  (Exploit Prediction Scoring System — FIRST.org)
            Free, no auth. Provides 0.0–1.0 probability of exploitation in next 30 days per CVE.
            Added to every CVE record as epss_score + epss_percentile fields.

Architecture:
  EventBridge cron (daily, 07:00 UTC) OR GitHub Actions workflow_dispatch
  → Lambda (this file)
      → Fetch CISA KEV JSON
      → Upsert every CVE into relayshield_intel_cve (full record, 180d TTL)
      → For new ransomware-flagged entries: write relayshield_intel_iocs (ioc_type=cve)
        AND append a kev_ransomware_active marker to relayshield_intel_alerts
      → Telegram digest to ADMIN_CHAT_ID (new entries since last run)
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_CVE_TABLE   = "relayshield_intel_cve"
INTEL_IOCS_TABLE  = "relayshield_intel_iocs"
TG_SECRET_NAME    = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID     = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

CVE_TTL_DAYS      = 180   # KEV catalog entries kept longer than routine IOCs
IOC_TTL_DAYS      = 90    # matches existing relayshield_intel_iocs convention

KEV_JSON_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

_sm       = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bot_token() -> str:
    raw = _sm.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"]
    return json.loads(raw)["telegram_bot_token"]


def _send_telegram(token: str, chat_id: int, text: str) -> None:
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req     = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)


def _fetch_kev_catalog() -> list[dict]:
    req = urllib.request.Request(KEV_JSON_URL, headers={"User-Agent": "RelayShield/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("vulnerabilities", [])


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _upsert_cve(table, entry: dict) -> bool:
    """Write/refresh a CVE record. Returns True if this CVE is new (first time seen)."""
    cve_id = entry.get("cveID", "").strip()
    if not cve_id:
        return False

    ttl = Decimal(int(time.time()) + CVE_TTL_DAYS * 86400)
    is_new = False
    try:
        table.put_item(
            Item={"cve_id": cve_id},
            ConditionExpression="attribute_not_exists(cve_id)",
        )
        is_new = True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        is_new = False

    item = {
        "cve_id":                       cve_id,
        "vendor_project":               entry.get("vendorProject", ""),
        "product":                      entry.get("product", ""),
        "vulnerability_name":           entry.get("vulnerabilityName", ""),
        "date_added":                   entry.get("dateAdded", ""),
        "short_description":            entry.get("shortDescription", "")[:500],
        "required_action":              entry.get("requiredAction", "")[:500],
        "due_date":                     entry.get("dueDate", ""),
        "known_ransomware_campaign_use": entry.get("knownRansomwareCampaignUse", "Unknown"),
        # Every record written by this function comes from the CISA KEV
        # catalog by construction — unlike the GitHub Advisory / OSV sources
        # that share this table, so in_kev=True is always correct here.
        "in_kev":                       True,
        "ttl":                          ttl,
    }
    # epss_score/epss_percentile are attached to `entry` by the caller before
    # this runs (bug found 2026-07-07: they were computed but never actually
    # persisted here, so handle_tech_stack_cve's epss_score>0.1 filter and
    # in_kev check silently excluded every KEV entry, including CVE-2025-3248
    # / Langflow, from tech-stack-cve results despite the CVE being ingested).
    if "epss_score" in entry:
        item["epss_score"] = entry["epss_score"]
    if "epss_percentile" in entry:
        item["epss_percentile"] = entry["epss_percentile"]
    table.put_item(Item=item)
    return is_new


def _write_ransomware_ioc(table, entry: dict) -> bool:
    """Write a ransomware-flagged CVE into the shared IOC table. Returns True if newly written."""
    cve_id = entry.get("cveID", "").strip()
    now_ts = datetime.now(timezone.utc).isoformat()
    ttl    = Decimal(int(time.time()) + IOC_TTL_DAYS * 86400)
    try:
        table.put_item(
            Item={
                "ioc_value":  cve_id.lower(),
                "seen_ts":    now_ts,
                "ioc_type":   "cve",
                "channel":    "cisa_kev",
                "category":   "ransomware_active_exploitation",
                # A7, 2026-08-27. This used to write vendorProject + product
                # into "malware", so CISA KEV rows indexed values like
                # "Microsoft Windows" as malware families. "malware" is the
                # malware-index GSI hash key, which is what a customer's
                # hunting query matches on, so every KEV row was adding a
                # vendor name to a namespace of malware names. A query for a
                # real family never matches these, and browsing the namespace
                # shows vendors sitting among families.
                #
                # The affected product is worth keeping, so it moves to its own
                # attribute. "malware" is left unset: KEV publishes an exploited
                # product, and does not name the malware exploiting it.
                # knownRansomwareCampaignUse says only Known/Unknown, which is
                # not a family name either.
                "affected_product": " ".join(
                    (entry.get("vendorProject", "") + " " + entry.get("product", "")).split()
                ),
                "ttl":        ttl,
            },
            ConditionExpression="attribute_not_exists(ioc_value)",
        )
        return True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    except Exception as exc:
        logger.warning("KEV IOC write failed %s: %s", cve_id, exc)
        return False


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

EPSS_API_URL         = "https://api.first.org/data/v1/epss"
NVD_API_URL          = "https://services.nvd.nist.gov/rest/json/cves/2.0"
OSV_API_URL          = "https://api.osv.dev/v1/query"
GITHUB_ADVISORY_URL  = "https://api.github.com/graphql"
VULNCHECK_KEV_URL    = "https://api.vulncheck.com/v3/index/vulncheck-kev"
GITHUB_TOKEN_SECRET  = "relayshield/github_search_token"
USERS_TABLE          = "relayshield_users"


def _fetch_epss_scores(cve_ids: list[str]) -> dict[str, dict]:
    """Fetch EPSS exploitation probability scores for a batch of CVE IDs.
    Returns {cve_id: {score: float, percentile: float}}.
    EPSS API supports up to 500 CVEs per request — batched automatically."""
    scores: dict[str, dict] = {}
    batch_size = 400
    for i in range(0, len(cve_ids), batch_size):
        batch = cve_ids[i:i + batch_size]
        params = "&".join(f"cve={cve}" for cve in batch)
        url    = f"{EPSS_API_URL}?{params}&envelope=true&pretty=false"
        try:
            req  = urllib.request.Request(url, headers={"User-Agent": "RelayShield-KEV/1.0"})
            resp = json.loads(urllib.request.urlopen(req, timeout=20).read())
            for item in resp.get("data", []):
                cve = item.get("cve", "").upper()
                if cve:
                    scores[cve] = {
                        "epss_score":       round(float(item.get("epss", 0)), 4),
                        "epss_percentile":  round(float(item.get("percentile", 0)), 4),
                    }
        except Exception as exc:
            logger.warning("EPSS batch fetch failed (i=%d): %s", i, exc)
    return scores


def lambda_handler(event, context):
    # deploy_lambdas.yml invokes every function it deploys to prove the module
    # imported — update-function-code reports success even when the package is
    # missing a module, and the failure only shows up as Runtime.ImportModuleError
    # on the next real invocation. Reaching this line already proves the import
    # worked, so return before doing any work: a full KEV+NVD+OSV pass takes long
    # enough that the CLI's read timeout would fire, and the probe swallows that,
    # which would make the check pass without asserting anything.
    if isinstance(event, dict) and event.get("source") == "ci.import-probe":
        logger.info("ci.import-probe — module imported, returning without ingesting")
        return {"statusCode": 200, "probe": "ok"}

    logger.info("INTEL-FEED-4 (CISA KEV + EPSS + NVD + OSV + GitHub Advisory) starting")

    cve_table  = _dynamodb.Table(INTEL_CVE_TABLE)
    ioc_table  = _dynamodb.Table(INTEL_IOCS_TABLE)
    users_table = _dynamodb.Table(USERS_TABLE)
    bot_token  = _get_bot_token()

    try:
        vulns = _fetch_kev_catalog()
    except Exception as exc:
        logger.error("CISA KEV fetch failed: %s", exc)
        return {"statusCode": 502, "error": str(exc)}

    # ── Source 2: NVD CVSS enrichment — enrich CVEs with CVSS v3 scores ──
    # Rate limit: 5 req/30s without API key — we batch new CVEs only
    nvd_enriched = 0
    try:
        import time as _time
        for i, entry in enumerate(new_cves[:50]):   # cap at 50 to avoid timeout
            cve_id = entry.get("cveID", "")
            if not cve_id:
                continue
            if i > 0 and i % 5 == 0:
                _time.sleep(30)  # respect 5/30s rate limit
            try:
                nvd_url = f"{NVD_API_URL}?cveId={cve_id}"
                nvd_req = urllib.request.Request(
                    nvd_url, headers={"User-Agent": "RelayShield/1.0"}
                )
                nvd_resp = json.loads(urllib.request.urlopen(nvd_req, timeout=10).read())
                vulns = nvd_resp.get("vulnerabilities", [])
                if vulns:
                    metrics = vulns[0].get("cve", {}).get("metrics", {})
                    cvss_v3 = metrics.get("cvssMetricV31", metrics.get("cvssMetricV30", []))
                    if cvss_v3:
                        score = cvss_v3[0].get("cvssData", {})
                        cve_table.update_item(
                            Key={"cve_id": cve_id},
                            UpdateExpression="SET cvss_v3_score = :s, cvss_v3_severity = :sv, cvss_v3_vector = :v",
                            ExpressionAttributeValues={
                                ":s":  boto3.dynamodb.types.Decimal(str(score.get("baseScore", 0))),
                                ":sv": score.get("baseSeverity", ""),
                                ":v":  score.get("vectorString", ""),
                            },
                        )
                        nvd_enriched += 1
            except Exception as nvd_exc:
                logger.debug("NVD enrich failed %s: %s", cve_id, nvd_exc)
    except Exception as exc:
        logger.warning("NVD CVSS enrichment failed: %s", exc)

    # ── Source 5: GitHub Security Advisory (GraphQL) ──
    ghsa_new = 0
    try:
        gh_secret = _sm.get_secret_value(SecretId=GITHUB_TOKEN_SECRET)["SecretString"]
        gh_token  = json.loads(gh_secret).get("token", gh_secret.strip())
        if gh_token and gh_token != "PLACEHOLDER":
            gh_query = """
            {
              securityAdvisories(first: 50, orderBy: {field: PUBLISHED_AT, direction: DESC}) {
                nodes {
                  ghsaId identifiers { type value }
                  summary severity
                  cvss { score vectorString }
                  vulnerabilities(first: 5) {
                    nodes { package { name ecosystem } vulnerableVersionRange }
                  }
                }
              }
            }
            """
            gh_req = urllib.request.Request(
                GITHUB_ADVISORY_URL,
                data=json.dumps({"query": gh_query}).encode(),
                headers={
                    "Authorization": f"bearer {gh_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "RelayShield/1.0",
                },
                method="POST",
            )
            gh_resp = json.loads(urllib.request.urlopen(gh_req, timeout=15).read())
            advisories = gh_resp.get("data", {}).get("securityAdvisories", {}).get("nodes", [])
            for adv in advisories:
                # Extract CVE ID if present
                cve_ref = next(
                    (i["value"] for i in adv.get("identifiers", []) if i["type"] == "CVE"), None
                )
                ghsa_id = adv.get("ghsaId", "")
                key     = cve_ref or ghsa_id
                if not key:
                    continue
                pkgs = [
                    f"{v['package']['ecosystem']}:{v['package']['name']}"
                    for v in adv.get("vulnerabilities", {}).get("nodes", [])
                    if v.get("package")
                ]
                try:
                    cve_table.put_item(
                        Item={
                            "cve_id":           key,
                            "ghsa_id":          ghsa_id,
                            "vendor_project":   "GitHub Advisory",
                            "product":          ", ".join(pkgs[:3]),
                            "vulnerability_name": adv.get("summary", "")[:200],
                            "short_description": adv.get("summary", "")[:500],
                            "cvss_v3_score":    boto3.dynamodb.types.Decimal(str(adv.get("cvss", {}).get("score", 0) or 0)),
                            "cvss_v3_severity": adv.get("severity", ""),
                            "source":           "github_advisory",
                            "known_ransomware_use": "Unknown",
                            "ttl":              boto3.dynamodb.types.Decimal(int(time.time()) + 180 * 86400),
                        },
                        ConditionExpression="attribute_not_exists(cve_id)",
                    )
                    ghsa_new += 1
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("GitHub Advisory fetch failed: %s", exc)

    # Fetch EPSS scores for all CVEs in this run
    cve_ids     = [e.get("cveID", "") for e in vulns if e.get("cveID")]
    epss_scores = _fetch_epss_scores(cve_ids)
    logger.info("EPSS scores fetched for %d/%d CVEs", len(epss_scores), len(cve_ids))

    new_cves      = []
    new_ransomware = []

    for entry in vulns:
        # Attach EPSS score before upsert
        cve_id = entry.get("cveID", "")
        if cve_id in epss_scores:
            entry["epss_score"]      = Decimal(str(epss_scores[cve_id]["epss_score"]))
            entry["epss_percentile"] = Decimal(str(epss_scores[cve_id]["epss_percentile"]))
        is_new = _upsert_cve(cve_table, entry)
        if is_new:
            new_cves.append(entry)
        if str(entry.get("knownRansomwareCampaignUse", "")).lower() == "known":
            if _write_ransomware_ioc(ioc_table, entry):
                new_ransomware.append(entry)

    summary_lines = [
        f"<b>RelayShield INTEL-FEED-4 — CISA KEV</b>",
        f"Total catalog size: {len(vulns)}",
        f"New CVEs added: {len(new_cves)}",
        f"New ransomware-flagged CVEs: {len(new_ransomware)}",
    ]
    for entry in new_ransomware[:10]:
        epss = float(entry.get("epss_score", 0))
        epss_str = f" EPSS:{epss:.1%}" if epss > 0 else ""
        summary_lines.append(
            f"⚠️ {entry.get('cveID')} — {entry.get('vendorProject')} {entry.get('product')} "
            f"(ransomware-active){epss_str}"
        )
    # Show top EPSS scores among all KEV entries (highest exploitation probability)
    top_epss = sorted(
        [(e.get("cveID",""), float(e.get("epss_score", 0))) for e in vulns if e.get("epss_score", 0) > 0],
        key=lambda x: x[1], reverse=True
    )[:3]
    if top_epss:
        summary_lines.append(f"\n🎯 Highest EPSS exploitation probability:")
        for cve, score in top_epss:
            summary_lines.append(f"  {cve}: {score:.1%}")

    # ── Source 3: OSV (Google Open Source Vulnerabilities) — no auth ──
    osv_new = 0
    try:
        osv_req  = urllib.request.Request(
            f"{OSV_API_URL}",
            data=json.dumps({"package": {"ecosystem": "PyPI"}}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "RelayShield/1.0"},
            method="POST",
        )
        # OSV query is package-specific — we use it for enrichment of existing CVEs
        # by checking if a KEV CVE has OSV cross-references
        for entry in new_cves[:20]:   # enrich new CVEs only
            cve_id = entry.get("cveID", "")
            if not cve_id:
                continue
            osv_enrich_req = urllib.request.Request(
                OSV_API_URL,
                data=json.dumps({"query": {"version": "", "package": {}}, "id": cve_id}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "RelayShield/1.0"},
                method="POST",
            )
            try:
                osv_resp = json.loads(urllib.request.urlopen(osv_enrich_req, timeout=8).read())
                if osv_resp.get("vulns"):
                    cve_table.update_item(
                        Key={"cve_id": cve_id},
                        UpdateExpression="SET osv_confirmed = :t",
                        ExpressionAttributeValues={":t": True},
                    )
                    osv_new += 1
            except Exception:
                pass
    except Exception as exc:
        logger.warning("OSV enrichment failed: %s", exc)

    # ── Source 4: VulnCheck KEV extension (no auth for public feed) ──
    vulncheck_new = 0
    try:
        vc_req = urllib.request.Request(
            VULNCHECK_KEV_URL,
            headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"},
        )
        vc_resp = json.loads(urllib.request.urlopen(vc_req, timeout=20).read())
        vc_vulns = vc_resp.get("data", [])
        for vc in vc_vulns[:500]:   # top 500 only — rate-limited
            cve_id = (vc.get("cveID") or vc.get("cve_id") or "").strip().upper()
            if not cve_id or not cve_id.startswith("CVE-"):
                continue
            # Only add if not already in CISA KEV
            existing = cve_table.get_item(Key={"cve_id": cve_id}).get("Item")
            if not existing:
                ttl = Decimal(int(time.time()) + 180 * 86400)
                try:
                    cve_table.put_item(
                        Item={
                            "cve_id":                     cve_id,
                            "vendor_project":             vc.get("vendorProject", ""),
                            "product":                    vc.get("product", ""),
                            "vulnerability_name":         vc.get("vulnerabilityName", ""),
                            "date_added":                 vc.get("dateAdded", ""),
                            "short_description":          vc.get("shortDescription", "")[:500],
                            "known_ransomware_use":       str(vc.get("knownRansomwareCampaignUse", "Unknown")),
                            "source":                     "vulncheck_kev",
                            "ttl":                        ttl,
                        },
                        ConditionExpression="attribute_not_exists(cve_id)",
                    )
                    vulncheck_new += 1
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("VulnCheck KEV fetch failed: %s", exc)

    # ── Tech stack CVE targeting: alert users who declared affected products ──
    tech_alerts = 0
    if new_cves:
        try:
            users_resp = users_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("tech_stack").exists(),
                ProjectionExpression="user_id, tech_stack, telegram_chat_id",
            )
            for user in users_resp.get("Items", []):
                stack    = [s.lower() for s in (user.get("tech_stack") or [])]
                chat_id  = user.get("telegram_chat_id")
                if not stack or not chat_id:
                    continue
                for cve in new_cves:
                    product = (cve.get("product") or "").lower()
                    vendor  = (cve.get("vendor_project") or "").lower()
                    if any(s in product or s in vendor for s in stack):
                        epss    = float(cve.get("epss_score", 0))
                        epss_str = f" · EPSS: {epss:.0%}" if epss > 0 else ""
                        ransomware_flag = " 🦠 *ransomware-active*" if str(cve.get("known_ransomware_use","")).lower() == "known" else ""
                        msg = (
                            f"🎯 *RelayShield — CVE Targeting Alert*\n\n"
                            f"*{cve.get('cveID')}* affects *{cve.get('product')}* "
                            f"({cve.get('vendor_project')}) — a product in your declared tech stack.{ransomware_flag}\n\n"
                            f"*Severity:* Actively exploited (CISA KEV){epss_str}\n"
                            f"*Description:* {(cve.get('short_description') or '')[:200]}\n\n"
                            f"Patch immediately if running an affected version.\n\n"
                            f"🛡️ _RelayShield CVE Intelligence_"
                        )
                        _send_telegram(bot_token, int(chat_id), msg)
                        tech_alerts += 1
        except Exception as exc:
            logger.warning("Tech stack CVE alert failed: %s", exc)

    summary_lines.extend([
        f"\nNVD CVSS enriched: {nvd_enriched}",
        f"GitHub Advisory new: {ghsa_new}",
        f"OSV cross-referenced: {osv_new}",
        f"VulnCheck KEV new: {vulncheck_new}",
        f"Tech stack CVE alerts: {tech_alerts}",
    ])

    _send_telegram(bot_token, ADMIN_CHAT_ID, "\n".join(summary_lines))
    logger.info(
        "INTEL-FEED-4 complete: total=%d new_cves=%d new_ransomware=%d osv=%d vulncheck=%d",
        len(vulns), len(new_cves), len(new_ransomware), osv_new, vulncheck_new,
    )

    return {
        "statusCode":           200,
        "total_catalog_size":   len(vulns),
        "new_cves":             len(new_cves),
        "new_ransomware_cves":  len(new_ransomware),
        "osv_enriched":         osv_new,
        "vulncheck_new":        vulncheck_new,
        "tech_stack_alerts":    tech_alerts,
    }
