# await_http -- poll a URL until a freshly deployed route actually answers.
#
#   . "$(dirname "$0")/lib_await_route.sh"
#   await_http 204 -X OPTIONS "$URL" -H 'Origin: https://example.com'
#   echo "$AWAIT_STATUS"; cat "$AWAIT_BODY"; grep -i allow-origin "$AWAIT_HEADERS"
#
# WHY THIS EXISTS, AND WHY IT IS A SHARED FILE RATHER THAN A FOURTH COPY
# ---------------------------------------------------------------------
# `aws apigateway create-deployment` returns a deployment id BEFORE the edge
# serves the new resource set. A curl fired milliseconds later gets a 404 on
# routes that are entirely correct, which reads as a routing bug and sends
# somebody diagnosing something that was never wrong.
#
# THIS HAS NOW HAPPENED TWICE, AND THE SECOND TIME WAS AVOIDABLE.
# tools/create_mpp_settlement_lambda.sh hit it on 2026-09-05 and carries an
# inline retry with the diagnosis written above it. On 2026-09-09
# create_watchlist_routes.sh was written fresh, probed once, and hit the
# identical race -- because the knowledge lived in a neighbouring script's
# comments and nothing carried it across. A lesson recorded in one file is not
# a lesson the next file learns.
#
# It is the same class as the two failures already fixed inside
# create_watchlist_lambda.sh: an AWS call that SUCCEEDS, followed immediately by
# one that assumes it finished.
#
#     create-role       -> "the role cannot be assumed by Lambda"
#     create-function   -> "the function is in state: Pending"
#     create-deployment -> a 404 at the edge for a few seconds
#
# ONLY PROPAGATION-SHAPED ANSWERS ARE WAITED ON, which is the half that keeps
# this from hiding real faults. 403, 404 and a failed connection are what an
# undeployed route returns. ANY OTHER STATUS IS A REAL ANSWER from a component
# that is listening, so it returns immediately and lets the caller decide. A
# retry loop that waits out a 500 turns a clear fault into a slow one.

AWAIT_BODY="${TMPDIR:-/tmp}/rs_await_body.$$"
AWAIT_HEADERS="${TMPDIR:-/tmp}/rs_await_head.$$"

# await_http EXPECTED_STATUS [curl args ...]
# Sets AWAIT_STATUS, writes the body to $AWAIT_BODY and headers to $AWAIT_HEADERS.
# Returns 0 when EXPECTED_STATUS is seen, 1 otherwise.
await_http() {
  _await_expect=$1
  shift
  _await_max=${AWAIT_MAX:-12}
  _await_sleep=${AWAIT_SLEEP:-5}
  _await_n=1
  while :; do
    AWAIT_STATUS=$(curl -sS -D "$AWAIT_HEADERS" -o "$AWAIT_BODY" \
                     -w '%{http_code}' "$@" 2>/dev/null || echo 000)
    if [ "$AWAIT_STATUS" = "$_await_expect" ]; then
      return 0
    fi
    case "$AWAIT_STATUS" in
      403|404|000) ;;                 # what an undeployed route looks like
      *) return 1 ;;                  # a real answer; waiting would hide it
    esac
    if [ "$_await_n" -ge "$_await_max" ]; then
      return 1
    fi
    echo "   HTTP $AWAIT_STATUS -- the stage may not have reached the edge yet,"
    echo "                      retrying ($_await_n/$_await_max, this is normal"
    echo "                      for the first ~15 seconds after a deployment)"
    sleep "$_await_sleep"
    _await_n=$((_await_n + 1))
  done
}

await_cleanup() {
  rm -f "$AWAIT_BODY" "$AWAIT_HEADERS"
}
