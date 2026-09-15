#!/bin/sh
# Is an attribution key LIVE at the Mini App's edge?
#
#   sh tools/verify_miniapp_source_key.sh tg-miniapp-tonapp
#   sh tools/verify_miniapp_source_key.sh tg-miniapp-tonapp --local
#
# WHY THIS IS A SCRIPT AND NOT A LINE OF curl IN A CHAT REPLY. On 2026-09-15 I
# handed over this verification:
#
#     curl -sS https://app.relayshield.net/ | grep -c tg-miniapp-tonapp
#
# It returned 0, and the deploy had succeeded perfectly. The Worker resolves the
# key with `sourceFor(url.searchParams.get("startapp") || "")`, so a request
# with NO ?startapp= resolves to the generic "tg-miniapp" and the key being
# asked about can never appear in the response. THE PROBE COULD NOT RETURN 1 IN
# ANY STATE. That is this repo's own "a probe that takes a route the real client
# does not take proves nothing" rule, broken in the verification step of the
# very commit that deploys the key.
#
# THE THREE STATES ARE DIFFERENT PROBLEMS WITH DIFFERENT FIXES, so this names
# which one it got rather than printing a count:
#
#   LIVE        the key is in the deployed ALLOWED_SOURCES and is echoed back
#   DOWNGRADED  the edge answers, but with "tg-miniapp" -- the key is not in the
#               DEPLOYED allowlist. Registered on a branch, or the deploy did not
#               run. This is the state that looks like working attribution and
#               is not: every arrival is logged under the generic key.
#   UNREACHABLE the host did not answer at all. Says nothing about the key.
#
# It prints the BODY line it matched on, not a summary of it, because a check
# that says something is wrong owes the reader the evidence that says which.
set -e
KEY="$1"
[ -n "$KEY" ] || { echo "usage: $0 <source-key> [--local]"; exit 2; }

if [ "$2" = "--local" ]; then
  # The built artefact in THIS checkout, with no network involved. Answers
  # "would this deploy carry the key", never "is it deployed".
  ROOT=$(cd "$(dirname "$0")/.." && pwd)
  echo "reading the LOCAL build, not the live edge"
  if grep -q "\"$KEY\"" "$ROOT/cloudflare_worker_miniapp.js"; then
    echo "PRESENT in this checkout's ALLOWED_SOURCES."
    echo "That is a fact about the repo. Run without --local to ask the edge."
    exit 0
  fi
  echo "ABSENT from this checkout's ALLOWED_SOURCES."
  exit 1
fi

# RS_MINIAPP_ORIGIN exists so the LIVE code path can be EXERCISED against a
# local render rather than only read -- app.relayshield.net is egress-blocked
# from the build container, and a probe nobody has run is exactly what this
# script was written to replace.
ORIGIN="${RS_MINIAPP_ORIGIN:-https://app.relayshield.net}"
URL="$ORIGIN/?startapp=$KEY"
echo "GET $URL"
BODY=$(curl -sS --max-time 20 "$URL" 2>&1) || {
  echo "UNREACHABLE: the request failed. This says nothing about the key."
  echo "$BODY"
  exit 1
}

LINE=$(printf '%s' "$BODY" | grep -o 'const SOURCE = "[^"]*"' | head -1)
if [ -z "$LINE" ]; then
  echo "UNREACHABLE: something answered, but it is not the Mini App page."
  printf '%s' "$BODY" | head -c 400
  echo
  exit 1
fi

echo "$LINE"
case "$LINE" in
  *"\"$KEY\""*)
    echo "LIVE: the edge recognises $KEY and echoes it into the page."
    exit 0
    ;;
  *)
    echo "DOWNGRADED: the edge answered but resolved to the generic key, so"
    echo "$KEY is not in the DEPLOYED ALLOWED_SOURCES. Every arrival on this"
    echo "route would be logged as tg-miniapp. Check that main carries the key"
    echo "and that Deploy Telegram Mini App ran green on that commit."
    exit 1
    ;;
esac
