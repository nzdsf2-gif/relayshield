#!/bin/sh
# Why did a check inside the Mini App say "Could not complete the check"?
#
#   sh tools/diagnose_miniapp_check.sh UQDO5ehz1nYveujnMV5q5yHdDj--jJuedeYo83n8jnuGMqqt
#
# THE CARD CANNOT TELL YOU, AND THAT IS THE POINT. check() resolves to
# ok:false for every failure shape there is -- a timeout, a rejected fetch, a
# non-2xx, a body the browser discarded -- so the phone shows one card for four
# different problems with four different fixes. This prints the BODY and the
# HEADERS of what the API actually returns, which separates them in one run:
#
#   HTTP 200, ok:true         the API is fine; the failure was in the browser
#                             (CORS, or the 4s timeout in check()).
#
# THE 4-SECOND TIMEOUT IS THE ONE A STATUS CODE CANNOT SHOW YOU, so this
# measures it. check() passes timeoutMs = 4000 to AbortSignal.timeout, and an
# abort throws, and check()'s catch-all returns a verdict with raw = {}. So a
# response that is perfectly correct but SLOW renders exactly the same card as
# a rejected one, with no reason line under it, because there is no body to
# read a reason out of. Step 2 below re-sends the request with curl capped at
# the same 4 seconds: if step 1 answers 200 and step 2 times out, the API is
# not broken and our own deadline is what the user hit.
#   HTTP 429                  the daily KEYLESS PER-IP CAP. Not an outage. The
#                             Mini App now renders this reason, but only
#                             because the 429 carries allow-origin -- check
#                             that header is present in the output below.
#   HTTP 5xx / a traceback    ours, in handle_wallet_risk or its TON upstream.
#   no allow-origin header    the browser discards the response AFTER it
#                             arrives, so the app sees a failure and the log
#                             shows a success. curl cannot see this, which is
#                             why the header is printed rather than assumed.
#
# Read-only. No credentials, no AWS. Runs anywhere with network, which is why
# it is here rather than in a chat reply: api.relayshield.net is egress-blocked
# from the build container, so this could not be run before it shipped.
# UNVERIFIED against the live host for that reason; the request shape is the
# one widget/relayshield-widget.js sends, copied from its own post().
set -e
TARGET="$1"
[ -n "$TARGET" ] || { echo "usage: $0 <url-or-address>"; exit 2; }

# RS_API_ORIGIN exists so this script's own branches can be EXERCISED against a
# local server rather than only read: api.relayshield.net is egress-blocked from
# the build container, and an unrun diagnostic is how a verification step ships
# that cannot return a pass in any state. Leave it unset for the real host.
ORIGIN="${RS_API_ORIGIN:-https://api.relayshield.net}"

case "$TARGET" in
  http://*|https://*) PATH_="/v1/link-check"; FIELD="url" ;;
  *)                  PATH_="/v1/wallet-risk"; FIELD="address" ;;
esac

echo "STEP 1 -- what the API returns, with no deadline of ours in the way"
echo "POST $ORIGIN$PATH_  ($FIELD)"
echo
curl -sS -i --max-time 30 \
  -w '\n\nTIMING  connect %{time_connect}s  first byte %{time_starttransfer}s  total %{time_total}s\n' \
  -X POST "$ORIGIN$PATH_" \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: relayshield-widget/1.0' \
  -H 'Origin: https://app.relayshield.net' \
  -d "{\"$FIELD\":\"$TARGET\",\"source\":\"tg-miniapp\"}"
echo
echo "----------------------------------------------------------------------"
echo "STEP 2 -- the SAME request under the app's own 4-second deadline"
echo
# The -w line is captured rather than printed straight out: curl writes it on
# failure too, so a timed-out request would otherwise announce itself as
# "ANSWERED IN 4.00s with HTTP 000", which is the opposite of what happened.
if S2=$(curl -sS -o /dev/null --max-time 4 \
     -w 'ANSWERED IN %{time_total}s with HTTP %{http_code}' \
     -X POST "$ORIGIN$PATH_" \
     -H 'Content-Type: application/json' \
     -H 'User-Agent: relayshield-widget/1.0' \
     -H 'Origin: https://app.relayshield.net' \
     -d "{\"$FIELD\":\"$TARGET\",\"source\":\"tg-miniapp\"}" 2>/dev/null)
then
  echo "$S2"
else
  echo "TIMED OUT AT 4s -- this is the app's own deadline, not an API failure."
  echo "check() aborts here, the catch-all returns raw = {}, and the card says"
  echo "\"Could not complete the check\" with no reason, because there is no body."
fi
echo
echo "----------------------------------------------------------------------"
echo "HOW TO READ IT"
echo
echo "  step 1 non-2xx                  the API answered and said why. Read the body."
echo "  step 1 2xx, no allow-origin     a success the browser THROWS AWAY. Ours to fix."
echo "  step 1 2xx fast, step 2 fine    the API is healthy; look at the client."
echo "  step 1 2xx SLOW, step 2 times   our 4s deadline is what the user hit."
echo "  connection refused / no answer  says nothing either way. Re-run once."
