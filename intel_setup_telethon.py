"""
INTEL-2 One-Time Telethon Setup Script
Run this LOCALLY (not in Lambda) to authenticate and store the session.

Prerequisites:
  pip install telethon boto3

SETTING UP A SECOND OR THIRD ACCOUNT -- the short version
---------------------------------------------------------
Two things: a SIM, and one code.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python intel_setup_telethon.py \\
      --secret relayshield/telethon_session_prospecting

It reads api_id and api_hash out of the existing secret, asks for the new
account's phone number, and then asks for the 5-digit code Telegram sends to
that handset. That is the whole thing. No my.telegram.org, no web login code,
no api_id or api_hash to find or type.

This works because **api_id and api_hash identify an APPLICATION, not an
account.** One pair covers every Telegram account we will ever run, so only the
FIRST account ever needs to register one. Everything below applies to that first
account, or to `--new-app`.

FOUR VALUES EXIST AND TWO OF THEM ARE "A CODE TELEGRAM JUST SENT YOU"
---------------------------------------------------------------------
That is the whole reason this is confusing:

  1. my.telegram.org web login code -- ALPHANUMERIC, e.g. "Jn5c7SPap0E".
     Goes in the my.telegram.org login box, nowhere else, ever.
  2. api_id   -- an integer, from API Development Tools. Permanent.
  3. api_hash -- 32 lowercase hex characters, same page. Permanent.
  4. Telethon login code -- 5 DIGITS, arrives when this script connects.

The reuse path above needs only 4. The manual path needs all four.

Steps for the FIRST account only:
  1. Get API credentials from my.telegram.org:
     - Log in (this is where code 1 is used) → API Development Tools →
       Create new application
     - App title: RelayShield Intel (or any name)
     - Copy api_id (integer) and api_hash (32 hex chars)

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


def _read_app_credentials(secret_name: str) -> tuple[str, str]:
    """Pull api_id and api_hash out of an existing session secret.

    api_id and api_hash identify an APPLICATION, not an account. The same pair
    works for any number of Telegram accounts, so a second or third account does
    not need its own -- which means it does not need a my.telegram.org trip, and
    the whole alphanumeric web-login-code step disappears.

    This reads ONLY those two fields. The session_string in that secret is the
    live collection session and is never read, never used to connect, and never
    written anywhere by this function.
    """
    sm = boto3.Session(profile_name="relayshield").client(
        "secretsmanager", region_name=REGION)
    blob = json.loads(sm.get_secret_value(SecretId=secret_name)["SecretString"])
    return str(blob["api_id"]), str(blob["api_hash"])


async def _setup(secret_name: str, walk_channels: bool, reuse_app_from: str):
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print("ERROR: Install telethon first: pip install telethon")
        return

    print("\n=== RelayShield INTEL-2 Telethon Setup ===\n")

    if reuse_app_from:
        print(f"Reusing the app credentials already stored in {reuse_app_from}.")
        print("api_id and api_hash identify an APPLICATION, not an account, so a")
        print("second account needs neither a new pair nor a my.telegram.org login.")
        print("Only that secret's api_id and api_hash are read. Its session string,")
        print("which is the live collection session, is not touched.\n")
        try:
            api_id, api_hash = _read_app_credentials(reuse_app_from)
        except Exception as exc:
            print(f"Could not read {reuse_app_from}: {exc}")
            print("Re-run with --new-app to enter api_id and api_hash by hand.")
            return
        print(f"api_id {api_id} loaded.\n")

        phone = input("Enter the phone number for the NEW account (e.g. +12025551234): ").strip()
        if not phone.startswith("+") or not phone[1:].replace(" ", "").isdigit():
            print("\nThat is not a phone number in international format.")
            print("It must start with + and a country code, e.g. +12025551234.")
            return

        print(f"\nConnecting to Telegram with phone {phone}...")
        print("Telegram sends a 5-digit code to that number's Telegram app.")
        print("That code is the only thing left to type.")
        return await _authenticate(
            TelegramClient, StringSession, api_id, api_hash, phone,
            secret_name, walk_channels,
        )

    print("Get your API credentials from: https://my.telegram.org")
    print("Log in → API Development Tools → Create new application\n")

    # Validate before connecting. On 2026-08-29 the my.telegram.org web login
    # code was entered at the api_id prompt, and the script accepted it.
    #
    # FOUR different values are in play, which is three more than anyone should
    # have to hold in their head:
    #
    #   1. my.telegram.org web login code -- ALPHANUMERIC, e.g. "Jn5c7SPap0E".
    #      Arrives in Telegram, goes in the my.telegram.org login box, nowhere
    #      else, ever.
    #   2. api_id   -- an integer. Identifies an APPLICATION, not an account.
    #   3. api_hash -- 32 lowercase hex characters, same page as api_id.
    #   4. Telethon login code -- 5 DIGITS, arrives in Telegram when the client
    #      below connects. Different code, different format, different purpose.
    #
    # 1 and 4 are both "a code Telegram just sent you", which is exactly why
    # they get confused. Note that the reuse path above skips 1, 2 and 3
    # entirely: prefer it.
    #
    # Failing here costs nothing. Failing after the login code burns it and
    # needs another, so these checks come first.
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
    print("Telegram sends a 5-digit code to that number's Telegram app.")
    return await _authenticate(
        TelegramClient, StringSession, api_id, api_hash, phone,
        secret_name, walk_channels,
    )


async def _authenticate(TelegramClient, StringSession, api_id, api_hash, phone,
                        secret_name, walk_channels):
    """Log in, optionally check channel access, and store the session.

    Shared by both paths, so the reuse path and the manual path cannot drift
    apart -- in particular the create-if-missing secret write and the
    channel-walk guard apply identically to each.
    """
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
    ap.add_argument("--new-app", action="store_true",
                    help="Register a brand-new application on my.telegram.org and "
                         "type api_id and api_hash in by hand. Only needed for the "
                         "very first account; every later one reuses the existing "
                         "pair, because they identify an application and not an "
                         "account.")
    args = ap.parse_args()

    is_collection = args.secret == DEFAULT_SECRET
    walk_channels = args.walk_channels or is_collection

    # Reuse the existing application credentials for any account that is not the
    # first. This is the whole simplification: api_id and api_hash belong to an
    # APPLICATION, so a second or third Telegram account needs neither its own
    # pair nor a my.telegram.org login to get one. That removes the alphanumeric
    # web login code from the process entirely and leaves exactly one code to
    # type -- the 5-digit one Telegram sends when the client connects.
    #
    # Setting up the collection account itself, or explicitly asking for a new
    # app, still takes the manual path.
    reuse_app_from = "" if (is_collection or args.new_app) else DEFAULT_SECRET

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

    asyncio.run(_setup(args.secret, walk_channels, reuse_app_from))
