#!/bin/sh
# Wire the three /v1/watchlist/* routes, their CORS preflights, and prove one.
#
#   sh tools/create_watchlist_routes.sh
#
# Run from the repo root, on the Mac, AFTER tools/create_watchlist_lambda.sh has
# created relayshield-watchlist. Idempotent: every step checks for what it is
# about to create, so a re-run after a failure is safe.
#
# WHY A SCRIPT, same as create_link_check_endpoint.sh
# ---------------------------------------------------
# This API Gateway is NOT a {proxy+} catch-all. One resource and one method per
# endpoint, so a path that exists in the Lambda's ROUTES returns
# 403 "Missing Authentication Token" at the edge until the gateway knows about
# it -- an auth-shaped error for a routing problem, which is the single most
# misleading failure this gateway produces.
#
# THE OPTIONS METHODS ARE NOT OPTIONAL
# ------------------------------------
# The Mini App runs on its own hostname and posts `content-type:
# application/json`, which is not a CORS-safelisted value, so the browser sends
# an OPTIONS PREFLIGHT to each path before it will send the POST. A preflight
# that 403s means the real request is NEVER SENT, and the only visible symptom
# is a button that does nothing -- with no request in the Lambda's logs at all,
# because the request never reached it.
#
# The OPTIONS methods integrate with the SAME Lambda rather than a MOCK, so the
# allowed headers and methods have exactly one definition (_CORS in
# relayshield_watchlist.py). A MOCK integration would put a second copy of those
# headers in gateway configuration, where nothing tests it and nothing would
# notice it drifting from the handler.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-watchlist
PARTS="add list remove"

export AWS_PAGER=""

aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing changed." >&2
  echo "620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 2. Does the Lambda actually route these paths?"
# Read from the source rather than assumed. A gateway route pointing at a path
# the handler does not know returns our own 404 body, which looks like a bug in
# the handler rather than a typo in this script.
for P in $PARTS; do
  if grep -q "\"/v1/watchlist/$P\"" relayshield_watchlist.py; then
    echo "   /v1/watchlist/$P is in ROUTES"
  else
    echo "STOP: relayshield_watchlist.py has no route for /v1/watchlist/$P." >&2
    exit 1
  fi
done
echo

echo "== 3. Does the function exist and is it Active?"
STATE=$(aws lambda get-function --function-name "$FUNC" \
          --query 'Configuration.State' --output text 2>/dev/null || echo MISSING)
if [ "$STATE" = "MISSING" ]; then
  echo "STOP: $FUNC does not exist. Run tools/create_watchlist_lambda.sh first." >&2
  exit 1
fi
if [ "$STATE" != "Active" ]; then
  echo "   state is $STATE, waiting for Active"
  aws lambda wait function-active-v2 --function-name "$FUNC"
fi
echo "   $FUNC is Active"
echo

echo "== 4. The /v1/watchlist parent resource"
V1_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
          --query "items[?path=='/v1'].id | [0]" --output text)
if [ -z "$V1_ID" ] || [ "$V1_ID" = "None" ]; then
  echo "STOP: no /v1 resource on API $API_ID. Wrong API id?" >&2
  exit 1
fi
echo "   /v1 -> $V1_ID"

WL_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
          --query "items[?path=='/v1/watchlist'].id | [0]" --output text)
if [ -n "$WL_ID" ] && [ "$WL_ID" != "None" ]; then
  echo "   /v1/watchlist already exists -> $WL_ID"
else
  WL_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
            --parent-id "$V1_ID" --path-part watchlist --query 'id' --output text)
  echo "   created /v1/watchlist -> $WL_ID"
fi
echo

LAMBDA_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"
URI="arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations"

for P in $PARTS; do
  echo "== 5.$P  /v1/watchlist/$P"
  RES_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
             --query "items[?path=='/v1/watchlist/$P'].id | [0]" --output text)
  if [ -n "$RES_ID" ] && [ "$RES_ID" != "None" ]; then
    echo "   resource exists -> $RES_ID"
  else
    RES_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
               --parent-id "$WL_ID" --path-part "$P" --query 'id' --output text)
    echo "   created -> $RES_ID"
  fi

  # POST and OPTIONS are created the same way. Authorization NONE and no API key
  # on both: these endpoints authenticate with Telegram's SIGNED initData in the
  # body, which is stronger than an API key for this purpose because it proves
  # WHICH user is asking. An API key would prove only that the caller has a key.
  for M in POST OPTIONS; do
    if aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
         --http-method "$M" >/dev/null 2>&1; then
      echo "   $M already exists -- leaving it alone"
    else
      aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
        --http-method "$M" --authorization-type NONE --no-api-key-required \
        --query 'httpMethod' --output text >/dev/null
      aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$RES_ID" \
        --http-method "$M" --type AWS_PROXY --integration-http-method POST \
        --uri "$URI" --query 'type' --output text >/dev/null
      echo "   $M created and integrated with $FUNC"
    fi
  done

  # A fixed statement id makes a re-run collide with itself rather than stacking
  # duplicate permissions. The source ARN uses * for the method so one statement
  # covers POST and OPTIONS on this path.
  aws lambda add-permission --function-name "$FUNC" \
    --statement-id "apigw-watchlist-$P" --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/*/v1/watchlist/$P" \
    --query 'Statement' --output text >/dev/null 2>&1 \
    && echo "   invoke permission added" \
    || echo "   invoke permission already present"
  echo
done

echo "== 6. Deploy the $STAGE stage"
# A gateway change is invisible until the stage is redeployed. Skipping this
# leaves every path 403 while the console shows all six methods configured.
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --description "add /v1/watchlist/{add,list,remove} for the Telegram Mini App" \
  --query 'id' --output text
echo

echo "== 7. Prove it end to end"
BASE="https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE/v1/watchlist"

# THE PREFLIGHT IS CHECKED FIRST AND SEPARATELY, because it is the half that
# fails invisibly. curl ignores CORS entirely, so a POST can look perfect from a
# terminal while every browser refuses to send it.
echo "   OPTIONS $BASE/list"
PRE=$(curl -sS -o /dev/null -w '%{http_code}' -X OPTIONS "$BASE/list" \
        -H 'Origin: https://miniapp.relayshield.net' \
        -H 'Access-Control-Request-Method: POST' \
        -H 'Access-Control-Request-Headers: content-type' || true)
ACAO=$(curl -sS -D - -o /dev/null -X OPTIONS "$BASE/list" \
        -H 'Origin: https://miniapp.relayshield.net' \
        -H 'Access-Control-Request-Method: POST' \
        -H 'Access-Control-Request-Headers: content-type' 2>/dev/null \
        | tr -d '\r' | awk 'tolower($1) == "access-control-allow-origin:" {print $2}')
echo "   -> $PRE, access-control-allow-origin: ${ACAO:-NONE}"
if [ "$PRE" != "204" ] || [ -z "$ACAO" ]; then
  echo "STOP: the preflight did not succeed with an allow-origin header." >&2
  echo "The POST below may still pass from curl, and the Mini App will still be" >&2
  echo "dead in a browser. Fix this before believing step 7b." >&2
  exit 1
fi
echo

echo "   POST $BASE/list with no initData (must be REFUSED, by us)"
BODY=$(curl -sS -X POST "$BASE/list" -H 'Content-Type: application/json' -d '{}' || true)
echo "   $BODY"
echo
case "$BODY" in
  *"unverified"*)
    # This is the success case and it is worth being explicit about why a
    # REFUSAL proves the wiring. It proves three things at once: the gateway
    # routed the path (not "Missing Authentication Token"), our handler ran
    # (that string exists nowhere else), and the identity gate is ON -- an
    # unsigned request cannot read anybody's watchlist.
    echo "LIVE. The gateway routes to our handler and the identity gate refuses"
    echo "an unsigned request, which is exactly right."
    echo
    echo "The remaining half cannot be tested with curl: a real call carries"
    echo "Telegram's signed initData, which only Telegram can mint. Open the"
    echo "Mini App inside Telegram and add a watch."
    ;;
  *"Missing Authentication Token"*)
    echo "STOP: the gateway still does not know this path. Re-run; if it" >&2
    echo "persists, check that step 6 deployed the $STAGE stage." >&2
    exit 1
    ;;
  *"Forbidden"*)
    echo "STOP: 403. API Key Required is probably still true on the POST method." >&2
    exit 1
    ;;
  *"Internal server error"*)
    echo "STOP: the Lambda raised. Read its log; the likeliest cause is a" >&2
    echo "missing permission on the pepper secret or the KMS alias." >&2
    echo "  AWS_PROFILE=relayshield aws logs tail /aws/lambda/$FUNC --since 5m" >&2
    exit 1
    ;;
  *)
    echo "STOP: unexpected response. The route exists but the handler did not" >&2
    echo "answer as expected." >&2
    exit 1
    ;;
esac
