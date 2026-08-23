"""
RelayShield OSINT-2 Part 1 -- LLM-based channel classification.

Triages the `category=pending_review` backlog in relayshield_intel_channels
(candidates auto-discovered via @mention/t.me-link scraping, never manually
reviewed) using Claude Haiku 4.5 via Amazon Bedrock. Zero new vendor/secret --
same AWS IAM already used everywhere else in this account.

Why Bedrock, not the direct Anthropic API: no new API key/secret to manage,
same IAM role pattern as every other intel Lambda. Cross-region inference
profile required for invocation (us.anthropic.claude-haiku-4-5-20251001-v1:0)
-- the bare foundation-model ID alone is rejected for on-demand throughput on
this model.

Classification signal is deliberately narrow: channel username + description
+ discovery provenance (keyword_match / discovery_method / found_via) --
that's all that's stored per channel, no message content. For a large
fraction of pending_review entries (auto-discovered via cross-promotion or
@mention scraping) the description is just the username itself, giving the
model very little to go on. The prompt is written to default to REJECT (not
approve) when there isn't enough signal to be reasonably confident -- a false
negative here just leaves a candidate in pending_review for a human/future
pass; a false positive re-introduces exactly the noise-channel problem that
prompted this classifier in the first place (see the cross-promotion crawl
cleanup, 2026-07-24).

DynamoDB table: relayshield_intel_channels
  On APPROVE: active=True, category set to the model's inferred category
  On REJECT: category="rejected_by_classifier" (active stays False) -- a
    distinct terminal state from "pending_review" so a rejected candidate
    isn't re-classified every run, but is still queryable/auditable rather
    than silently deleted.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CHANNELS_TABLE = "relayshield_intel_channels"
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
BEDROCK_REGION = "us-east-1"

# MUST match INTEL_CATEGORIES in relayshield_intel_monitor.py. The monitor
# renders a per-category label and severity on every user alert, so a category
# this classifier can emit but the monitor does not know degrades that alert
# silently -- no error, no log line. test_intel_category_drift.py enforces the
# match; do not edit one side without the other.
#
# "card_shop" added 2026-08-21: the monitor has always had a label and a
# severity for it, but nothing anywhere could ever produce one, so it was a
# dead branch. Stolen-card shops are a real and distinct channel type.
VALID_CATEGORIES = {
    "infostealer", "credential_dump", "ransomware", "crypto",
    "phaas", "sim_swap", "card_shop", "hacktivist", "general",
}

_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

SYSTEM_PROMPT = """You triage candidate Telegram channel names for a cybercrime threat-intelligence \
pipeline. Each candidate was auto-discovered by scraping @mentions or t.me links out of messages \
in already-tracked criminal/OSINT channels -- most are noise (personal accounts, email-provider \
names parsed out of email addresses in breach-dump text, random crypto-chat participants), not \
real threat-intel sources.

Approve a channel ONLY if the username and/or description gives real, specific signal that it's a \
criminal marketplace, stealer-log/credential-dump channel, ransomware-gang channel, phishing-kit \
vendor, SIM-swap market, or general cyber-threat-intel feed. Default to REJECT when signal is \
thin, generic, or looks like a personal account/email-provider name/reserved word -- a missed \
approval just leaves a candidate for a later pass; a wrong approval reintroduces exactly the \
noise problem this classifier exists to fix.

Respond with ONLY a JSON object, no other text:
{"approve": true|false, "category": "infostealer"|"credential_dump"|"ransomware"|"crypto"|"phaas"|"sim_swap"|"general", "confidence": "high"|"medium"|"low", "reason": "<one short phrase>"}

category is only meaningful when approve=true; use "general" as a safe default when approving \
something that doesn't fit a narrower bucket."""


def _classify_one(username: str, description: str, provenance: str) -> dict:
    user_prompt = (
        f"username: {username}\n"
        f"description: {description}\n"
        f"discovery context: {provenance}"
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    })
    resp = _bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
    payload = json.loads(resp["body"].read())
    text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    result = json.loads(text)
    if "approve" not in result:
        raise ValueError(f"malformed classifier response: {text[:200]}")
    if result.get("approve") and result.get("category") not in VALID_CATEGORIES:
        result["category"] = "general"
    return result


def run_classification(limit: int = 200, apply: bool = True) -> dict:
    """Classify the pending_review backlog.

    `apply=False` is a real dry run: it still calls Bedrock (that is the part
    worth previewing -- the verdicts) but writes nothing back to DynamoDB. The
    backlog has never been triaged, so the first pass should be read before it
    is committed; a false approve re-introduces exactly the noise-channel
    problem this classifier exists to remove, and there is no undo.
    """
    table = _dynamodb.Table(CHANNELS_TABLE)

    resp = table.scan(FilterExpression=Attr("category").eq("pending_review"))
    candidates = resp.get("Items", [])
    while "LastEvaluatedKey" in resp and len(candidates) < limit:
        resp = table.scan(
            FilterExpression=Attr("category").eq("pending_review"),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        candidates.extend(resp.get("Items", []))
    candidates = candidates[:limit]

    logger.info("OSINT-2 classifier: %d pending_review candidates to process", len(candidates))

    stats = {"processed": 0, "approved": 0, "rejected": 0, "errors": 0,
             "applied": bool(apply), "candidates": len(candidates)}
    now_ts = datetime.now(timezone.utc).isoformat()

    for item in candidates:
        username = item.get("username", "")
        description = item.get("description", "") or username
        provenance = (
            f"discovery_method={item.get('discovery_method', 'mention_scrape')}, "
            f"found_via={item.get('discovered_from') or item.get('found_via', 'unknown')}, "
            f"keyword_match={item.get('keyword_match', 'n/a')}"
        )
        try:
            result = _classify_one(username, description, provenance)
        except Exception as exc:
            logger.warning("Classification failed for @%s: %s", username, exc)
            stats["errors"] += 1
            continue

        stats["processed"] += 1
        if result.get("approve"):
            if not apply:
                stats["approved"] += 1
                logger.info("[DRY RUN] would APPROVE @%s -> category=%s (%s)",
                            username, result["category"], result.get("reason", ""))
                continue
            table.update_item(
                Key={"username": username},
                UpdateExpression="SET active = :a, category = :c, classified_at = :t, classifier_reason = :r",
                ExpressionAttributeValues={
                    ":a": True,
                    ":c": result["category"],
                    ":t": now_ts,
                    ":r": result.get("reason", ""),
                },
            )
            stats["approved"] += 1
            logger.info("APPROVED @%s -> category=%s (%s)", username, result["category"], result.get("reason", ""))
        else:
            if not apply:
                stats["rejected"] += 1
                logger.info("[DRY RUN] would REJECT @%s (%s)", username, result.get("reason", ""))
                continue
            table.update_item(
                Key={"username": username},
                UpdateExpression="SET category = :c, classified_at = :t, classifier_reason = :r",
                ExpressionAttributeValues={
                    ":c": "rejected_by_classifier",
                    ":t": now_ts,
                    ":r": result.get("reason", ""),
                },
            )
            stats["rejected"] += 1

        time.sleep(0.1)  # light rate-limit courtesy pause between Bedrock calls

    logger.info("OSINT-2 classifier complete: %s", stats)
    return stats


def lambda_handler(event, context):
    event = event or {}
    # The CI import probe invokes every deployed function with this payload.
    # Returning before the scan matters here more than elsewhere: a probe that
    # fell through would run a full Bedrock pass over the backlog on every
    # deploy, and with apply defaulting to True it would COMMIT those verdicts.
    if event.get("source") == "ci.import-probe":
        return {"statusCode": 200, "skipped": "ci.import-probe"}
    stats = run_classification(
        limit=int(event.get("limit", 200)),
        apply=bool(event.get("apply", True)),
    )
    return {"statusCode": 200, **stats}


def main() -> int:
    """CLI entry point, so the backlog can be triaged from CI or a laptop.

    Dry run by default. `--apply` is the only thing that writes.
    """
    import argparse

    ap = argparse.ArgumentParser(description="Triage the pending_review channel backlog.")
    ap.add_argument("--limit", type=int, default=200, help="max candidates to classify")
    ap.add_argument("--apply", action="store_true",
                    help="write verdicts back to DynamoDB (default: dry run)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = run_classification(limit=args.limit, apply=args.apply)

    print("\n" + "=" * 60)
    print(f"candidates found : {stats['candidates']}")
    print(f"classified       : {stats['processed']}")
    print(f"would approve    : {stats['approved']}" if not args.apply
          else f"approved         : {stats['approved']}")
    print(f"would reject     : {stats['rejected']}" if not args.apply
          else f"rejected         : {stats['rejected']}")
    print(f"errors           : {stats['errors']}")
    if not args.apply:
        print("\nDRY RUN — nothing was written. Re-run with --apply to commit.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
