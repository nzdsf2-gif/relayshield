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

case "$TARGET" in
  http://*|https://*) PATH_="/v1/link-check"; FIELD="url" ;;
  *)                  PATH_="/v1/wallet-risk"; FIELD="address" ;;
esac

echo "POST https://api.relayshield.net$PATH_  ($FIELD)"
echo
curl -sS -i --max-time 20 \
  -X POST "https://api.relayshield.net$PATH_" \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: relayshield-widget/1.0' \
  -H 'Origin: https://app.relayshield.net' \
  -d "{\"$FIELD\":\"$TARGET\",\"source\":\"tg-miniapp\"}"
echo
echo
echo "READ THE STATUS AND THE access-control-allow-origin HEADER TOGETHER."
echo "A 2xx with no allow-origin is a success the Mini App still cannot use."
