"""
One-off, interactive script to regenerate the Telethon session string after
Telegram revokes it (AuthKeyDuplicatedError — "used under two different IP
addresses simultaneously").

Run this locally, NOT in Lambda — it needs a human to type in the login code
sent to the account's phone (and the 2FA password, if that account has one).

Usage:
    python3 regenerate_telethon_session.py

It reuses the existing api_id/api_hash from Secrets Manager (same Telegram
app registration), logs in fresh, prints the new session string, and prints
the exact AWS CLI command to update the secret. It does NOT write the secret
for you — review the output, then run the printed command yourself.

Takes relayshield_intel_monitor.py's own single-flight DynamoDB lock (same
table, same lock_id) before touching Telegram, and holds it for the whole
interactive login. Incident 2026-08-24: this script had no lock of its own,
overlapped with a scheduled Lambda invocation using the same session from a
different IP, and Telegram permanently revoked the auth key mid-login. The
Lambda's own lock only ever protected its two schedules from each other —
never this script. If the lock is already held (a scheduled run is in
flight), this exits without touching Telegram rather than risking another
collision — wait a few minutes and retry, or pause both EventBridge rules
first for a guaranteed-clear window.
"""

import json
import time

import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

SECRET_NAME = "relayshield/telethon_session"
REGION = "us-east-1"
PROFILE = "relayshield"

# Same table/lock_id as relayshield_intel_monitor.py's _acquire_lock/_release_lock
# — this has to be the identical lock, not a lookalike, or it doesn't mutually
# exclude against the Lambda at all.
LOCK_TABLE = "relayshield_intel_monitor_lock"
LOCK_ID = "singleton"
# Generous TTL for a human typing in a phone number, an OTP, and possibly a
# 2FA password — the Lambda's own 280s TTL is sized for its own 300s timeout,
# not for interactive use. Released explicitly in `finally` well before this
# expires in the common case; this is just the crash-safety ceiling.
LOCK_TTL_SECONDS = 900


def _acquire_lock(table) -> bool:
    now = int(time.time())
    try:
        table.put_item(
            Item={"lock_id": LOCK_ID, "ttl": Decimal(now + LOCK_TTL_SECONDS), "acquired_at": now},
            ConditionExpression="attribute_not_exists(lock_id) OR #ttl < :now",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": now},
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _release_lock(table) -> None:
    try:
        table.delete_item(Key={"lock_id": LOCK_ID})
    except Exception:
        print("Warning: failed to release the intel-monitor lock — it will "
              f"expire on its own in at most {LOCK_TTL_SECONDS}s.")


def main():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sm = session.client("secretsmanager")
    dynamodb = session.resource("dynamodb")
    lock_table = dynamodb.Table(LOCK_TABLE)

    print("Acquiring the intel-monitor single-flight lock before touching "
          "Telegram (shared with the Lambda's own scheduled runs)...")
    if not _acquire_lock(lock_table):
        print(
            "\nLock is currently held — a scheduled Lambda invocation is "
            "probably mid-run. Running the interactive login now risks the "
            "exact 2026-08-24 collision (Telegram revokes the session if it "
            "sees two IPs at once). Wait a few minutes and try again, or "
            "disable relayshield-intel-monitor-cron and "
            "relayshield-intel-monitor-fast in EventBridge first for a "
            "guaranteed-clear window."
        )
        return

    try:
        current = json.loads(sm.get_secret_value(SecretId=SECRET_NAME)["SecretString"])

        api_id = int(current["api_id"])
        api_hash = current["api_hash"]

        print(f"Using existing api_id/api_hash from {SECRET_NAME}.")
        print("Starting interactive login — you'll be prompted for the phone")
        print("number, then the code Telegram sends, then the 2FA password if")
        print("that account has one set.\n")

        with TelegramClient(StringSession(), api_id, api_hash) as client:
            client.start()
            new_session_string = client.session.save()

        print("\nLogin succeeded. New session string:\n")
        print(new_session_string)

        new_secret = dict(current)
        new_secret["session_string"] = new_session_string
        new_secret_json = json.dumps(new_secret)

        print("\nTo update the secret, run:\n")
        print(
            "aws secretsmanager put-secret-value "
            f"--secret-id {SECRET_NAME} "
            f"--secret-string '{new_secret_json}' "
            f"--profile {PROFILE} --region {REGION}"
        )
    finally:
        _release_lock(lock_table)
        print("\nLock released.")


if __name__ == "__main__":
    main()
