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

import argparse
import asyncio
import json
import sys

import boto3

# The secret this writes to. It is a PARAMETER, not a constant, as of
# 2026-08-28, and the reason matters: this script used to hardcode
# relayshield/telethon_session, which is the session relayshield-intel-monitor
# authenticates with. Running it to set up a SECOND account, for prospecting
# discovery, would have silently overwritten the collection session and stopped
# all 99 channels. The default is unchanged, so the original use still works
# exactly as before.
#
#   intel collection (existing):  relayshield/telethon_session
#   prospecting discovery (new):  relayshield/telethon_session_prospecting
#
# Never point two different Telegram accounts at one secret, and never run
# prospecting discovery on the collection session: the per-session flood limits
# are tight enough that a large discovery sweep would rate-limit or ban the
# account collection depends on.
DEFAULT_SECRET  = "relayshield/telethon_session"
REGION          = "us-east-1"


async def _setup(secret_name: str):
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
        SecretId     = secret_name,
        SecretString = secret_value,
    )

    print("✅ Session stored in Secrets Manager")
    print(f"   Secret: {secret_name}")
    print("\n🛡️  INTEL-2 setup complete — Lambda is ready to deploy")
    print("   The phone number is NOT stored — only the session string")
    print("   You can discard the OTP SIM after this step\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--secret", default=DEFAULT_SECRET,
                    help=f"Secrets Manager secret to write the session to "
                         f"(default: {DEFAULT_SECRET})")
    args = ap.parse_args()

    # Overwriting the collection session is the one mistake this script can make
    # that is both easy and expensive, so it has to be typed out on purpose.
    if args.secret == DEFAULT_SECRET:
        print(f"\nThis will OVERWRITE {DEFAULT_SECRET}, the session")
        print("relayshield-intel-monitor uses to collect from 99 channels.")
        print("For a SECOND account (prospecting discovery), stop and re-run with:")
        print("  --secret relayshield/telethon_session_prospecting\n")
        if input("Overwrite the collection session? Type OVERWRITE to continue: ").strip() != "OVERWRITE":
            print("Aborted. Nothing was written.")
            sys.exit(1)

    asyncio.run(_setup(args.secret))
