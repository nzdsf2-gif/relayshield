#!/bin/sh
# Why did the Stars button say "could not start the purchase"?
#
# READ-ONLY. It answers one question the screen cannot: WHAT TELEGRAM SAID.
#
# The gateway route, the function and the identity gate are all provable with
# curl and were proved by tools/diagnose_watchlist_routes.sh. The half that is
# not provable with curl is createInvoiceLink, because it needs the bot token
# and a verified user, so the only evidence is the Lambda's own log -- and
# until 2026-09-12 that log said "HTTP Error 400: Bad Request" and nothing
# else, because urllib raises on a non-2xx and Telegram puts the reason in the
# body. That is fixed; this script reads the line.
#
# EXPECT: a "createInvoiceLink HTTP 400: {...}" line whose body names the
#         reason, e.g. a description Telegram returns for the bot's state.
# NO LINES: nobody has pressed the button since the fix deployed. Press it in
#         the Mini App, wait ten seconds, run this again.
set -u
export AWS_PAGER=""
REGION=us-east-1
GROUP=/aws/lambda/relayshield-watchlist

echo "== 1. Which account?"
AWS_PROFILE=relayshield aws sts get-caller-identity \
  --query Account --output text --no-cli-pager | sed 's/^/   /'
echo "   (must be 239677749008)"
echo

echo "== 2. Is the deployed code the version that logs the body?"
# A fix that has not shipped cannot log anything. LastModified answers it.
AWS_PROFILE=relayshield aws lambda get-function-configuration \
  --function-name relayshield-watchlist --region "$REGION" --no-cli-pager \
  --query '[LastModified,State,CodeSize]' --output text | sed 's/^/   /'
echo "   If LastModified predates the fix, the log CANNOT carry the body yet."
echo "   deploy_lambdas.yml ships it on a push to main touching the .py."
echo

echo "== 3. Every createInvoiceLink line in the last 24h, newest last"
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$(python3 -c 'import time;print(int((time.time()-86400)*1000))')" \
  --filter-pattern '"createInvoiceLink"' \
  --query 'events[].message' --output text 2>&1 | sed 's/^/   /'
echo

echo "== 4. Any unhandled error in the same window"
# A raise BEFORE the try block -- _get_secret, for instance -- produces a
# traceback and a 502, which the Mini App shows as the unreachable message
# rather than ours. Different cause, different fix, so it is printed separately.
AWS_PROFILE=relayshield aws logs filter-log-events \
  --log-group-name "$GROUP" --region "$REGION" --no-cli-pager \
  --start-time "$(python3 -c 'import time;print(int((time.time()-86400)*1000))')" \
  --filter-pattern '?"Traceback" ?"Task timed out" ?"AccessDenied"' \
  --query 'events[].message' --output text 2>&1 | sed 's/^/   /'
echo

echo "== HOW TO READ IT"
echo "  A line in step 3 naming a description  -> that is the answer. Send it."
echo "  Step 3 empty, step 2 recent            -> the button has not been"
echo "                                            pressed since the fix landed."
echo "  AccessDenied on secretsmanager         -> the role lost the bot-token"
echo "                                            grant. Re-run"
echo "                                            sh tools/create_watchlist_lambda.sh"
echo "                                            which re-applies it and is"
echo "                                            idempotent."
echo "  Traceback with no createInvoiceLink    -> it failed BEFORE the call,"
echo "                                            so read the traceback, not"
echo "                                            Telegram."
