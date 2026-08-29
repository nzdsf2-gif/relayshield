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

  2. Have a DEDICATED PREPAID SIM ready, in a real handset you control.

     Do NOT use an SMS-rental service. The original version of this file
     recommended sms-activate.org; that recommendation is withdrawn as of
     2026-08-29. Rented numbers are recycled to the next renter, who can
     then request a login code and take the account, and Telegram bans the
     number ranges these services use in bulk. An account that collects
     from 99 criminal channels, or one that will be used for prospecting
     under the RelayShield name, must sit on a number only we control.

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


async def _setup(secret_name: str, walk_channels: bool):
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("ERROR: Install telethon first: pip install telethon")
        return

    print("\n=== RelayShield INTEL-2 Telethon Setup ===\n")
    print("Get your API credentials from: https://my.telegram.org")
    print("Log in → API Development Tools → Create new application\n")

    # Validate before connecting. On 2026-08-29 the my.telegram.org LOGIN CODE
    # was entered at the api_id prompt -- an understandable mistake, because
    # getting these two values requires logging in first and the code is the
    # thing most recently on screen. Three distinct values are involved and
    # only two of them belong here:
    #
    #   login code  one-time secret, 5-6 digits, expires in minutes. Goes in the
    #               my.telegram.org login box and NOWHERE else, ever.
    #   api_id      integer, roughly 6-8 digits, from API Development Tools
    #   api_hash    32 lowercase hex characters, from the same page
    #
    # Failing here costs nothing. Failing after the OTP burns a code and needs
    # another one, so these checks come first.
    print("These come from my.telegram.org -> API Development Tools, AFTER you")
    print("log in. The one-time code you used to LOG IN is not either of them.\n")

    api_id = input("Enter api_id (an integer, e.g. 2040123): ").strip()
    if not api_id.isdigit():
        print(f"\nThat is not an api_id. Got {api_id!r}, which is not a number.")
        print("If it was the code Telegram just sent you, that is the LOGIN CODE:")
        print("it goes in the my.telegram.org login box. Log in, open API")
        print("Development Tools, create an app, and copy api_id from there.")
        return

    api_hash = input("Enter api_hash (32 hex characters): ").strip()
    if len(api_hash) != 32 or any(c not in "0123456789abcdef" for c in api_hash.lower()):
        print(f"\nThat is not an api_hash. It must be exactly 32 characters using")
        print(f"only 0-9 and a-f; got {len(api_hash)} character(s).")
        print("It is on the same API Development Tools page as the api_id.")
        return

    phone = input("Enter the phone number for THIS account (e.g. +12025551234): ").strip()
    if not phone.startswith("+") or not phone[1:].replace(" ", "").isdigit():
        print(f"\nThat does not look like a phone number in international format.")
        print("It must start with + and a country code, e.g. +12025551234.")
        return

    print(f"\nConnecting to Telegram with phone {phone}...")
    print("Telegram will send a login code to that number's Telegram app.")

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start(phone=phone)

    session_str = client.session.save()
    print("\n✅ Authentication successful")

    # Join monitoring channels
    # The channel walk resolves ~100 usernames back to back. Every one of them is
    # a ResolveUsernameRequest, which carries the tightest per-session flood limit
    # Telegram applies, and it runs on an account that is minutes old. That is a
    # reliable way to get a fresh account flood-waited or banned outright.
    #
    # For the COLLECTION account it is still worth doing once: the whole point of
    # that account is to reach those channels, and confirming access at setup is
    # cheaper than discovering a dead channel from a silent Lambda later.
    #
    # For any OTHER account it is both dangerous and pointless -- the prospecting
    # account has no business touching the collection channel list at all -- so it
    # is skipped unless explicitly asked for.
    if walk_channels:
        print("\nChecking access to monitored channels...")
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
        print(f"\nChannels: {joined} accessible, {skipped} unavailable")
    else:
        print("\nSkipping the monitored-channel walk (not the collection account).")
        print("~100 username resolves on a new account is how new accounts get banned.")

    await client.disconnect()

    # Store in Secrets Manager
    print("\nStoring session in Secrets Manager...")
    session = boto3.Session(profile_name="relayshield")
    sm      = session.client("secretsmanager", region_name=REGION)

    secret_value = json.dumps({
        "api_id":         api_id,
        "api_hash":       api_hash,
        "session_string": session_str,
    })

    # update_secret raises ResourceNotFoundException on a secret that does not
    # exist yet, which is exactly the case when setting up a SECOND account. The
    # failure would land AFTER the phone auth, so the OTP is spent and the session
    # string is lost -- and a second attempt needs a second OTP. Create it here
    # instead of asking for a console step that is easy to forget.
    try:
        sm.update_secret(SecretId=secret_name, SecretString=secret_value)
    except sm.exceptions.ResourceNotFoundException:
        print(f"   {secret_name} does not exist yet — creating it")
        sm.create_secret(Name=secret_name, SecretString=secret_value)

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
    ap.add_argument("--walk-channels", action="store_true",
                    help="Resolve every MONITORED_CHANNELS username to confirm "
                         "access. On by default for the collection secret only; "
                         "~100 resolves will flood-wait or ban a fresh account.")
    args = ap.parse_args()

    is_collection = args.secret == DEFAULT_SECRET
    walk_channels = args.walk_channels or is_collection

    # Overwriting the collection session is the one mistake this script can make
    # that is both easy and expensive, so it has to be typed out on purpose.
    if is_collection:
        print(f"\nThis will OVERWRITE {DEFAULT_SECRET}, the session")
        print("relayshield-intel-monitor uses to collect from 99 channels.")
        print("For a SECOND account (prospecting discovery), stop and re-run with:")
        print("  --secret relayshield/telethon_session_prospecting\n")
        if input("Overwrite the collection session? Type OVERWRITE to continue: ").strip() != "OVERWRITE":
            print("Aborted. Nothing was written.")
            sys.exit(1)

    asyncio.run(_setup(args.secret, walk_channels))
