#!/usr/bin/env python3
"""Print the WhatsApp front-door links, read from the live Twilio secret.

WHY THIS IS A TOOL AND NOT A CONSTANT IN THE REPO. The bot's WhatsApp number
lives in Secrets Manager (`relayshield/twilio_whatsapp_number`) and nowhere
else -- six handlers read it at runtime and not one of them hardcodes it. This
container has no AWS credentials, so a session cannot see it, and inventing an
E.164 number to fill a link would ship a front door pointing at a stranger.

So the work moves rather than stopping, which is this repo's standing rule for
anything that needs credentials: the script runs on the Mac and prints the
exact strings to paste into the two Workers that cannot read the secret
themselves.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield python3 tools/wa_front_door_link.py

READ-ONLY. It calls GetSecretValue and nothing else.

PLAIN python3, NOT ~/.rsvenv, AND THAT IS THE POINT. The first version imported
boto3, which meant the durable venv was a second thing that had to be right
before this could answer a one-line question -- and when it failed there was no
way to tell "the venv is missing" from "the file is not on this machine" from
"the secret is unreadable". It shells out to the AWS CLI instead, which every
other command in CLAUDE.md already assumes is installed, and falls back to
boto3 if the CLI is absent. Either route, --no-cli-pager, per rule 9.

THE NUMBER IS NOT A SECRET AND THIS TOOL STILL TREATS THE SECRET AS ONE. A
WhatsApp business number is public by construction -- every customer messages
it -- so committing it is fine. What must not leak is anything else in that
secret, so this prints the number and never the raw SecretString.

TWO UNWRAP SHAPES EXIST IN THE REPO FOR THIS ONE SECRET, and that is recorded
here because it is the shape that produced the dead bot-token call sites:
  relayshield_stripe_webhook.py   get_secret_json(..., "TWILIO_WHATSAPP_NUMBER")
  relayshield_breach_monitor.py   get_secret_plaintext(...)
Both work today because get_secret_json falls back to the raw string. This
tool accepts either, in that order, for the same reason.
"""

import argparse
import json
import pathlib
import re
import sys

SECRET_NAME = "relayshield/twilio_whatsapp_number"
SECRET_KEY = "TWILIO_WHATSAPP_NUMBER"

# One key per DESTINATION, never per category. A blog footer and a Mini App
# footer are different surfaces with different audiences, and sharing a key
# merges them into a number nobody can act on -- the tg-miniapp-channel defect
# the route table was rebuilt to remove.
ROUTES = [
    ("wa-blog",     "blog.relayshield.net footer"),
    ("wa-miniapp",  "Telegram Mini App footer"),
    ("wa-devs",     "api.relayshield.net/developers"),
    ("wa-email",    "checkemail@relayshield.net reply footer"),
]

# THE FILES THAT HOLD THE NUMBER AS A COMMITTED CONSTANT, and --write fills
# every one of them in a single pass.
#
# relayshield_developer_signup.py is deliberately NOT here: it is a Lambda, it
# already reads three secrets, and it reads this one at request time through
# _wa_number(). A Cloudflare Worker cannot do that, which is the only reason
# these three carry a constant at all.
#
# ONE COMMAND RATHER THAN THREE HAND EDITS, because "edit these three files and
# keep them equal" is a convention followed by hand, and this repo's own rule is
# that a convention followed by hand fails the first time somebody is in a
# hurry. Two of the three are pinned equal by test; the third would not have
# been, and that is exactly the copy that drifts.
WORKER_FILES = [
    "cloudflare_worker_blog.js",
    "cloudflare_worker_miniapp.js",
    "cloudflare_worker_checkemail.js",
]

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _raw_secret_via_cli() -> str | None:
    """Read the SecretString with the AWS CLI. None if the CLI is not here.

    --no-cli-pager because AWS CLI v2 pipes through a pager when stdout is a
    terminal, which stops a multi-command block dead at this line.
    """
    import shutil
    import subprocess
    if not shutil.which("aws"):
        return None
    proc = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value",
         "--secret-id", SECRET_NAME,
         "--query", "SecretString", "--output", "text",
         "--no-cli-pager"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        # NAMED, not swallowed. AccessDenied, ExpiredToken and
        # ResourceNotFound are three different problems with three different
        # fixes, and a bare "could not read the secret" sends the reader to
        # the wrong one.
        sys.exit("ERROR: the AWS CLI could not read the secret.\n"
                 f"       {proc.stderr.strip()}\n"
                 "       If this says ExpiredToken, refresh the profile. If it\n"
                 "       says AccessDenied, the profile is resolving to the\n"
                 "       wrong account -- check AWS_PROFILE=relayshield.")
    return proc.stdout.strip()


def read_number() -> str:
    raw = _raw_secret_via_cli()
    if raw is None:
        try:
            import boto3
        except ImportError:
            sys.exit("ERROR: neither the `aws` CLI nor boto3 is available.\n"
                     "       Install the AWS CLI, or run this with\n"
                     "       ~/.rsvenv/bin/python (see CLAUDE.md).")
        raw = boto3.client("secretsmanager").get_secret_value(
            SecretId=SECRET_NAME)["SecretString"].strip()
    try:
        value = json.loads(raw)[SECRET_KEY]
    except (json.JSONDecodeError, KeyError, TypeError):
        value = raw
    # Handlers store it as Twilio's channel form; wa.me wants bare digits.
    value = str(value).strip()
    if value.lower().startswith("whatsapp:"):
        value = value.split(":", 1)[1].strip()
    if not value.startswith("+"):
        value = "+" + value.lstrip("+")
    return value


def write_workers(digits: str) -> list:
    """Set `const WA_NUMBER = "<digits>";` in every Worker. Returns those changed.

    IT REFUSES TO CREATE THE LINE, and only ever replaces one that is already
    there. A tool that appends a constant to a file it does not find one in
    would happily add a second WA_NUMBER below the first, where JavaScript's
    own rules make the LAST declaration a SyntaxError rather than an override --
    so the Worker would stop deploying and the error would name a line nobody
    wrote by hand.
    """
    import re as _re
    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = _re.compile(r'(const WA_NUMBER\s*=\s*")([^"]*)(";)')
    changed = []
    for name in WORKER_FILES:
        path = root / name
        if not path.exists():
            print(f"  WARNING: {name} is not here, so it was not written.")
            continue
        text = path.read_text()
        hits = pattern.findall(text)
        if not hits:
            print(f"  WARNING: {name} declares no WA_NUMBER constant. Skipped "
                  "rather than appending one.")
            continue
        if len(hits) > 1:
            print(f"  WARNING: {name} declares WA_NUMBER {len(hits)} times. "
                  "Refusing to guess which one is live.")
            continue
        if hits[0][1] == digits:
            continue
        path.write_text(pattern.sub(r'\g<1>' + digits + r'\g<3>', text, count=1))
        changed.append(name)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--number", help="skip the secret read and use this E.164 "
                                     "number instead (for checking the output "
                                     "shape without AWS)")
    ap.add_argument("--write", action="store_true",
                    help="write WA_NUMBER into every Worker that carries it, "
                         "instead of printing it to be pasted by hand")
    args = ap.parse_args()

    number = args.number.strip() if args.number else read_number()

    if not E164.match(number):
        # A malformed number produces a wa.me link that resolves to nothing,
        # and wa.me answers 200 with a "phone number shared via url is
        # invalid" PAGE rather than a 404 -- so a broken link looks live to
        # every probe. Refuse here instead.
        sys.exit(f"ERROR: {number!r} is not E.164 (+ then 7-15 digits). "
                 "Refusing to print a link that would look live and go nowhere.")

    digits = number.lstrip("+")

    print(f"WhatsApp front door, from {SECRET_NAME}\n")
    print(f"  WA_NUMBER = \"{digits}\"   <- paste this into the Workers\n")
    print("Full links, for checking by hand:\n")
    for key, where in ROUTES:
        print(f"  {where}")
        print(f"    https://wa.me/{digits}?text=SRC_{key}\n")
    if args.write:
        print("WRITING THE CONSTANT\n")
        changed = write_workers(digits)
        if not changed:
            print("  nothing to do: every Worker already carries this number.\n")
        else:
            for name in changed:
                print(f"  updated {name}")
            print("\n  Commit and push these, then deploy. A constant changed on")
            print("  your Mac is not a constant on the edge.\n")

    print("The token is parsed and STRIPPED by parse_wa_source() in")
    print("relayshield_whatsapp_webhook.py, before the user lookup, so an")
    print("arrival from a number we have never seen is still attributed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
