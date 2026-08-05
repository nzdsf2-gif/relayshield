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
"""

import json
import boto3
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

SECRET_NAME = "relayshield/telethon_session"
REGION = "us-east-1"
PROFILE = "relayshield"


def main():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    sm = session.client("secretsmanager")
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


if __name__ == "__main__":
    main()
