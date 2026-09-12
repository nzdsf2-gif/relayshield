#!/bin/sh
# Why does OPTIONS /v1/watchlist/list return 404? Read-only, one run, no guessing.
#
#   sh tools/diagnose_watchlist_routes.sh
#
# WHY THIS EXISTS
# ---------------
# create_watchlist_routes.sh stopped at step 7 with:
#
#     -> 404, access-control-allow-origin: NONE
#
# and that is ALL it printed, because the check captured the status code and
# threw the body away. That is this repo's own "a status code describes your
# REQUEST, not the resource" rule broken inside the tool written to enforce it:
# a 404 from API Gateway and a 404 from our own handler are different problems
# with different fixes, and the BODY is the only thing that tells them apart.
#
# FOUR CANDIDATE CAUSES, and they are not narrowable from a status code alone:
#
#   A. THE GATEWAY NEVER ROUTED IT. Body is {"message": ...} -- API Gateway's
#      own shape, which our handler never produces. Means the resource, the
#      method or the deployment did not take.
#   B. OUR HANDLER ANSWERED, AND THE DEPLOYED CODE IS STALE. Body is
#      {"ok": false, "error": "unknown path ..."} with NO access-control
#      header, because the pre-CORS version of the file had none. Means
#      create_watchlist_lambda.sh ran before the CORS commit was merged, or the
#      update-function-code step did not run.
#   C. OUR HANDLER ANSWERED AND THE PATH IS NOT WHAT WE ASSUMED. Same body
#      shape as B, but the error NAMES the path it was given -- if that reads
#      /prod/v1/watchlist/list then the stage prefix is arriving in event.path
#      and ROUTES will never match it.
#   D. THE OPTIONS METHOD EXISTS BUT IS NOT INTEGRATED WITH THE FUNCTION.
#
# Step 6 settles B against A and D outright by invoking the function DIRECTLY
# with the gateway taken out of the path. That is the move that made
# diagnose_agent_bait_routes.sh pay for itself on its first run: when two causes
# produce the same symptom, ask the component in isolation.
#
# Every command here is a read. Nothing is created, changed or deployed.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-watchlist

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Account"
GOT=$(aws sts get-caller-identity --query Account --output text)
echo "   $GOT"
[ "$GOT" = "$ACCOUNT" ] || { echo "STOP: not $ACCOUNT. Nothing else here is meaningful." >&2; exit 1; }
echo

echo "== 2. Every gateway resource whose path mentions watchlist"
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'watchlist')].[id,path]" --output text | sort -k2
echo "   (no rows above means the resources were never created)"
echo

echo "== 3. Is anything greedy sitting above them?"
# An explicit resource beats a {proxy+}, so this is usually not the cause -- but
# it is one read and it removes a question rather than leaving it open.
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'{proxy+}') || contains(path,'{')].[id,path]" --output text | sort -k2
echo

echo "== 4. The methods and integrations on each watchlist path"
for P in add list remove; do
  RID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
          --query "items[?path=='/v1/watchlist/$P'].id | [0]" --output text)
  echo "   /v1/watchlist/$P -> ${RID}"
  if [ -z "$RID" ] || [ "$RID" = "None" ]; then
    echo "     NO RESOURCE. Cause A."
    continue
  fi
  for M in POST OPTIONS; do
    AUTH=$(aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$RID" \
             --http-method "$M" --query '[authorizationType,apiKeyRequired]' \
             --output text 2>/dev/null || echo "NO-METHOD")
    URI=$(aws apigateway get-integration --rest-api-id "$API_ID" --resource-id "$RID" \
            --http-method "$M" --query '[type,uri]' --output text 2>/dev/null \
            || echo "NO-INTEGRATION")
    echo "     $M  auth=$AUTH"
    echo "         $URI"
  done
done
echo

echo "== 5. Is the stage serving a deployment made AFTER those methods?"
# A gateway change is invisible until the stage is redeployed, and a stage
# pointing at an older deployment looks identical from the outside to a method
# that was never created.
aws apigateway get-stage --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --query '[deploymentId,lastUpdatedDate]' --output text
echo "   most recent deployments on this API:"
aws apigateway get-deployments --rest-api-id "$API_ID" \
  --query 'reverse(sort_by(items,&createdDate))[:3].[id,createdDate,description]' \
  --output text
echo "   The stage's deploymentId must be one of these, and newer than the methods."
echo

echo "== 6. THE DECISIVE ONE: ask the function directly, gateway out of the path"
# If this returns 204 with an access-control-allow-origin header, the deployed
# code IS the CORS version and the problem is entirely in the gateway (A or D).
# If it returns 404, the deployed code is STALE (B) and no amount of gateway
# work will fix it.
OUT=$(mktemp)
aws lambda invoke --function-name "$FUNC" \
  --payload '{"path":"/v1/watchlist/list","httpMethod":"OPTIONS"}' \
  --cli-binary-format raw-in-base64-out "$OUT" >/dev/null
echo "   synthetic OPTIONS event ->"
cat "$OUT"; echo
echo
echo "   EXPECT on current code : {\"statusCode\": 204, \"headers\": {... access-control-allow-origin ...}}"
echo "   IF IT SAYS 404         : the DEPLOYED CODE IS STALE. Cause B."
echo "                            Fix: re-run sh tools/create_watchlist_lambda.sh"
echo "                            AFTER merging, which calls update-function-code."
aws lambda get-function-configuration --function-name "$FUNC" \
  --query '[LastModified,State,LastUpdateStatus,CodeSize]' --output text
rm -f "$OUT"
echo

echo "== 7. What the edge actually answers, WITH THE BODY THIS TIME"
BASE="https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE/v1/watchlist"
echo "   --- OPTIONS $BASE/list"
curl -sS -i -X OPTIONS "$BASE/list" \
  -H 'Origin: https://miniapp.relayshield.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' | sed 's/^/   /'
echo
echo "   --- POST $BASE/list"
curl -sS -i -X POST "$BASE/list" -H 'Content-Type: application/json' -d '{}' | sed 's/^/   /'
echo
# THE STARS ROUTE, PROBED BY NAME. It was added to the Lambda's ROUTES table and
# to the create script's PARTS list on 2026-09-11, AFTER this API's resources were
# last created, so it is the one most likely to be missing at the edge -- and a
# missing invoice route means the buy button opens nothing. Probed separately
# because "the other three work" says nothing about this one.
echo "   --- POST $BASE/invoice   (the Stars route)"
curl -sS -i -X POST "$BASE/invoice" -H 'Content-Type: application/json' -d '{}' \
  | sed 's/^/   /'
echo

echo "   --- a route known to work, for comparison: POST /v1/link-check"
curl -sS -o /dev/null -w '   %{http_code}\n' -X POST \
  "https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE/v1/link-check" \
  -H 'Content-Type: application/json' -d '{"url":"https://example.com"}'
echo

echo "== HOW TO READ IT"
echo "  Body {\"message\": ...}            -> API Gateway answered. Cause A or D:"
echo "                                       read steps 4 and 5."
echo "  Body {\"ok\": false, \"error\":       -> OUR handler answered."
echo "        \"unknown path X\"}             If X begins /prod the stage prefix is"
echo "                                       arriving in event.path (cause C)."
echo "                                       If X is /v1/watchlist/list and step 6"
echo "                                       returned 204, the code is fine and the"
echo "                                       gateway is sending OPTIONS somewhere"
echo "                                       unexpected."
# CORRECTED 2026-09-12, ON THIS PROBE'S FIRST REAL RUN. It predicted that a
# missing route answers {"message": ...} from API Gateway. It does not, because
# of the /{proxy+} in step 3: the request falls through to relayshield-api, which
# 404s in OUR envelope with its own wording. So "our handler answered" was NOT
# proof the route existed, and three different components can 404 here.
#
# THE DISCRIMINATOR IS THE CORS HEADERS, not the envelope. relayshield_watchlist
# puts access-control-allow-origin on EVERY response including its 404s;
# relayshield-api does not. Same lesson as the 402 that came from the wrong
# Lambda at the wrong price: verify the field that DIFFERS between them.
echo "  /invoice: {\"message\": ...}        -> API Gateway itself. Route missing and"
echo "                                       nothing greedy caught it."
echo "  /invoice: \"unknown endpoint: ...\" -> RELAYSHIELD-API answered, via /{proxy+}."
echo "        and NO access-control header   THE ROUTE DOES NOT EXIST. This is the"
echo "                                       normal shape here, because of step 3."
echo "                                       Worse than a plain 404: with no CORS"
echo "                                       header the browser discards it, so the"
echo "                                       buy button fails SILENTLY in the app."
echo "                                       Fix: sh tools/create_watchlist_routes.sh"
echo "                                       An explicit resource beats /{proxy+},"
echo "                                       so the proxy needs no change."
echo "  /invoice: \"unknown path ...\"       -> relayshield-watchlist answered. The"
echo "        WITH access-control-allow-*    route EXISTS and its ROUTES table does"
echo "                                       not carry the path. A different bug."
echo "  /invoice: \"unverified: ...\"        -> the route exists and works. A refusal"
echo "                                       to an unsigned curl is the correct reply."
echo "  Step 6 says 404                    -> stale code (cause B). Nothing in the"
echo "                                       gateway is wrong. Re-run the create"
echo "                                       script after merging."
