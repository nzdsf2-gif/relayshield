"""
INTEL-2 One-Time Telethon Setup Script
Run this LOCALLY (not in Lambda) to authenticate and store the session.

Prerequisites:
  pip install telethon boto3

Steps:
  1. Get API credentials from my.telegram.org:
     - Log in → API Development Tools → Create new application
     - App title: RelayShield Intel (or any name)
     - Copy api_id (integer) and api_hash (string)

  2. Have your monitoring phone number ready (sms-activate.org number
     or dedicated prepaid SIM)

  3. Run: AWS_PROFILE=relayshield python3 intel_setup_telethon.py

  4. Enter api_id, api_hash, and phone number when prompted
     Telegram will send an OTP to the phone — enter it when prompted

  5. Script saves the session string to Secrets Manager automatically
     The phone number is never stored — only the session string

After this runs successfully, the Lambda will authenticate using the
stored session string on every invocation.
"""

import asyncio
import json
import time
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal

TELETHON_SECRET = "relayshield/telethon_session"
REGION          = "us-east-1"

# Same table/lock_id as relayshield_intel_monitor.py's _acquire_lock/
# _release_lock and regenerate_telethon_session.py's copy of it. Incident
# 2026-08-24: an unlocked script overlapped with a scheduled Lambda run using
# the same Telethon session from a different IP, and Telegram permanently
# revoked the auth key mid-login. This script writes straight to Secrets
# Manager with no review step, so the same collision here is worse, not
# better — must not skip the lock.
LOCK_TABLE = "relayshield_intel_monitor_lock"
LOCK_ID = "singleton"
LOCK_TTL_SECONDS = 900  # generous ceiling for a human typing in an OTP


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


async def _setup():
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("ERROR: Install telethon first: pip install telethon")
        return

    print("\n=== RelayShield INTEL-2 Telethon Setup ===\n")
    print("Get your API credentials from: https://my.telegram.org")
    print("Log in → API Development Tools → Create new application\n")

    api_id   = input("Enter api_id (integer from my.telegram.org): ").strip()
    api_hash = input("Enter api_hash (string from my.telegram.org): ").strip()
    phone    = input("Enter monitoring phone number (e.g. +12025551234): ").strip()

    lock_session = boto3.Session(profile_name="relayshield", region_name=REGION)
    lock_table = lock_session.resource("dynamodb").Table(LOCK_TABLE)

    print("\nAcquiring the intel-monitor single-flight lock before touching "
          "Telegram (shared with the Lambda's own scheduled runs)...")
    if not _acquire_lock(lock_table):
        print(
            "\nLock is currently held — a scheduled Lambda invocation is "
            "probably mid-run. Running this now risks the exact 2026-08-24 "
            "collision (Telegram revokes the session if it sees two IPs at "
            "once). Wait a few minutes and try again, or disable "
            "relayshield-intel-monitor-cron and relayshield-intel-monitor-fast "
            "in EventBridge first for a guaranteed-clear window."
        )
        return

    try:
        print(f"\nConnecting to Telegram with phone {phone}...")

        client = TelegramClient(StringSession(), int(api_id), api_hash)
        await client.start(phone=phone)

        session_str = client.session.save()
        print("\n✅ Authentication successful")

        # Join monitoring channels
        print("\nJoining monitored channels...")
        from relayshield_intel_monitor import MONITORED_CHANNELS
        joined = 0
        skipped = 0
        for username, category, desc in MONITORED_CHANNELS:
            try:
                await client.get_entity(username)
                print(f"  ✅ @{username} — accessible")
                joined += 1
            except Exception as exc:
                print(f"  ⚠️  @{username} — {exc}")
                skipped += 1

        await client.disconnect()
        print(f"\nChannels: {joined} accessible, {skipped} unavailable")

        # Store in Secrets Manager
        print("\nStoring session in Secrets Manager...")
        session = boto3.Session(profile_name="relayshield")
        sm      = session.client("secretsmanager", region_name=REGION)

        secret_value = json.dumps({
            "api_id":         api_id,
            "api_hash":       api_hash,
            "session_string": session_str,
        })

        sm.update_secret(
            SecretId     = TELETHON_SECRET,
            SecretString = secret_value,
        )

        print("✅ Session stored in Secrets Manager")
        print(f"   Secret: {TELETHON_SECRET}")
        print("\n🛡️  INTEL-2 setup complete — Lambda is ready to deploy")
        print("   The phone number is NOT stored — only the session string")
        print("   You can discard the OTP SIM after this step\n")
    finally:
        _release_lock(lock_table)
        print("Lock released.")


if __name__ == "__main__":
    asyncio.run(_setup())
