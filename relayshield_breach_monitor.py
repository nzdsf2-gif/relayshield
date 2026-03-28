"""
RelayShield Breach Monitor Lambda
Scans monitored emails against HIBP v3 and records new breach alerts.
"""

import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients (module-level for Lambda container reuse)
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE = "relayshield_breach_alerts"
SECRET_NAME = "relayshield/hibp_api_key"
HIBP_BASE_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/"
USER_AGENT = "RelayShield-BreachMonitor"

# HIBP Pwned 1 plan: 10 RPM → 1 request per 6 seconds
REQUEST_DELAY_SECONDS = 6
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 10  # doubles each retry on 429


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

def get_hibp_api_key() -> str:
    """Retrieve the HIBP API key from AWS Secrets Manager."""
    logger.info("Retrieving HIBP API key from Secrets Manager: %s", SECRET_NAME)
    response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
    secret = json.loads(response["SecretString"])
    api_key = secret["HIBP_API_KEY"]
    logger.info("Successfully retrieved HIBP API key.")
    return api_key


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_monitored_emails() -> list[dict]:
    """Return all records from relayshield_monitored_emails."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    items: list[dict] = []
    kwargs: dict = {}

    logger.info("Scanning table: %s", MONITORED_EMAILS_TABLE)
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    logger.info("Found %d monitored email record(s).", len(items))
    return items


def get_existing_breach_names(user_id: str, email_address: str) -> set[str]:
    """
    Return the set of breach names already recorded for this user/email pair
    in relayshield_breach_alerts.
    """
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("user_id").eq(user_id) & Attr("email_address").eq(email_address),
    }

    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    existing = {item["breach_name"] for item in items}
    logger.debug(
        "User %s / %s already has %d recorded breach(es).",
        user_id, email_address, len(existing),
    )
    return existing


def write_breach_alert(
    user_id: str,
    email_address: str,
    breach_name: str,
    breach_date: str,
    data_types_exposed: list[str],
    alert_sent_at: str,
) -> str:
    """Write a new breach alert record and return its alert_id."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    alert_id = str(uuid.uuid4())
    item = {
        "alert_id": alert_id,
        "user_id": user_id,
        "email_address": email_address,
        "breach_name": breach_name,
        "breach_date": breach_date,
        "data_types_exposed": data_types_exposed,
        "alert_sent_at": alert_sent_at,
        "remediation_status": "pending",
    }
    table.put_item(Item=item)
    logger.info(
        "Wrote breach alert %s for user %s: breach=%s",
        alert_id, user_id, breach_name,
    )
    return alert_id


def update_last_checked(email_id: str, timestamp: str) -> None:
    """Update last_checked on a monitored email record."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    table.update_item(
        Key={"email_id": email_id},
        UpdateExpression="SET last_checked = :ts",
        ExpressionAttributeValues={":ts": timestamp},
    )
    logger.info("Updated last_checked for email_id=%s to %s", email_id, timestamp)


# ---------------------------------------------------------------------------
# HIBP API
# ---------------------------------------------------------------------------

def call_hibp(email_address: str, api_key: str) -> list[dict] | None:
    """
    Call HIBP v3 breachedaccount for the given email.

    Returns:
        list[dict]  – breach objects on 200
        []          – empty list on 404 (no breaches found)
        None        – unrecoverable error after retries

    Raises nothing; all errors are logged and handled internally.
    """
    url = f"{HIBP_BASE_URL}{urllib.request.quote(email_address)}"
    headers = {
        "hibp-api-key": api_key,
        "user-agent": USER_AGENT,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                breaches: list[dict] = json.loads(body)
                logger.info(
                    "HIBP returned %d breach(es) for %s.", len(breaches), email_address
                )
                return breaches

        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # 404 = no breaches recorded for this address
                logger.info("No breaches found (404) for %s.", email_address)
                return []

            if exc.code == 429:
                wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Rate limited (429) on attempt %d/%d for %s. "
                    "Backing off %ds.",
                    attempt, MAX_RETRIES, email_address, wait,
                )
                time.sleep(wait)
                continue

            # Any other HTTP error is unexpected – log and abort this email
            logger.error(
                "HTTP %d from HIBP for %s: %s",
                exc.code, email_address, exc.reason,
            )
            return None

        except urllib.error.URLError as exc:
            logger.error(
                "Network error contacting HIBP for %s (attempt %d/%d): %s",
                email_address, attempt, MAX_RETRIES, exc.reason,
            )
            if attempt < MAX_RETRIES:
                backoff = BACKOFF_BASE_SECONDS * attempt
                logger.info("Retrying in %ds…", backoff)
                time.sleep(backoff)
                continue
            return None

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unexpected error calling HIBP for %s: %s", email_address, exc
            )
            return None

    logger.error(
        "Exhausted %d retries for %s. Skipping.", MAX_RETRIES, email_address
    )
    return None


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_email(monitored_record: dict, api_key: str) -> list[dict]:
    """
    Check a single monitored email against HIBP, persist new breaches,
    update last_checked, and return list of new breach summaries.
    """
    email_id = monitored_record["email_id"]
    user_id = monitored_record["user_id"]
    email_address = monitored_record["email_address"]
    now = datetime.now(timezone.utc).isoformat()

    logger.info("Processing email_id=%s (%s) for user_id=%s", email_id, email_address, user_id)

    breaches = call_hibp(email_address, api_key)

    if breaches is None:
        # Unrecoverable error – skip last_checked update so we retry next run
        logger.warning("Skipping last_checked update for email_id=%s due to HIBP error.", email_id)
        return []

    # Always update last_checked (even when no breaches / 404)
    update_last_checked(email_id, now)

    if not breaches:
        return []

    existing_breach_names = get_existing_breach_names(user_id, email_address)
    new_breaches: list[dict] = []

    for breach in breaches:
        breach_name = breach.get("Name", "")
        if not breach_name:
            logger.warning("Breach record missing Name field; skipping: %s", breach)
            continue

        if breach_name in existing_breach_names:
            logger.debug("Breach %s already recorded for %s — skipping.", breach_name, email_address)
            continue

        breach_date = breach.get("BreachDate", "")
        data_types_exposed = breach.get("DataClasses", [])

        alert_id = write_breach_alert(
            user_id=user_id,
            email_address=email_address,
            breach_name=breach_name,
            breach_date=breach_date,
            data_types_exposed=data_types_exposed,
            alert_sent_at=now,
        )

        new_breaches.append({
            "alert_id": alert_id,
            "user_id": user_id,
            "email_address": email_address,
            "breach_name": breach_name,
            "breach_date": breach_date,
        })

    logger.info(
        "email_id=%s: %d new breach(es) recorded out of %d returned by HIBP.",
        email_id, len(new_breaches), len(breaches),
    )
    return new_breaches


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    """
    Entry point for the RelayShield breach monitoring Lambda.

    Returns a summary payload with the total count and details of every
    new breach alert created in this invocation.
    """
    logger.info("RelayShield breach monitor started.")
    start_time = time.time()

    # 1. Fetch API key once per invocation
    try:
        api_key = get_hibp_api_key()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to retrieve HIBP API key: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve HIBP API key", "detail": str(exc)},
        }

    # 2. Load all monitored email records
    try:
        monitored_emails = scan_monitored_emails()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to scan monitored emails table: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to scan monitored emails", "detail": str(exc)},
        }

    if not monitored_emails:
        logger.info("No monitored emails found. Exiting.")
        return {"statusCode": 200, "body": {"new_breaches_found": 0, "new_breaches": []}}

    # 3. Process each email with rate-limit delay between calls
    all_new_breaches: list[dict] = []

    for index, record in enumerate(monitored_emails):
        # Enforce 6-second inter-request delay (HIBP 10 RPM limit).
        # Skip delay before the very first request.
        if index > 0:
            logger.info(
                "Waiting %ds before next HIBP request (%d/%d)…",
                REQUEST_DELAY_SECONDS, index + 1, len(monitored_emails),
            )
            time.sleep(REQUEST_DELAY_SECONDS)

        try:
            new_for_email = process_email(record, api_key)
            all_new_breaches.extend(new_for_email)
        except Exception as exc:  # noqa: BLE001
            # Catch-all so one bad record never aborts the whole run
            logger.exception(
                "Unhandled error processing email_id=%s: %s",
                record.get("email_id", "unknown"), exc,
            )

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "RelayShield breach monitor finished. "
        "%d email(s) checked, %d new breach(es) found. Elapsed: %ss.",
        len(monitored_emails), len(all_new_breaches), elapsed,
    )

    return {
        "statusCode": 200,
        "body": {
            "emails_checked": len(monitored_emails),
            "new_breaches_found": len(all_new_breaches),
            "new_breaches": all_new_breaches,
        },
    }
