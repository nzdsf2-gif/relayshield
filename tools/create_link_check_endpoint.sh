#!/bin/sh
# Expose POST /v1/link-check on the REST API, keyless, and prove it answers.
#
#   sh tools/create_link_check_endpoint.sh
#
# Run it from the repo root, on the Mac. Idempotent: every step checks for what
# it is about to create and skips it if it is already there, so a re-run after a
# failure is safe.
#
# WHY A SCRIPT
# ------------
# This API Gateway is NOT a {proxy+} catch-all. API_GATEWAY_SETUP.md step 2a
# creates one resource and one method per endpoint, so a route added to ROUTES
# in relayshield_api.py is live in the Lambda and returns 403 "Missing
# Authentication Token" at the edge until the gateway knows about it. Deploying
# the Lambda is therefore only half of shipping an endpoint, and the half that
# is missing fails in a way that reads like an auth problem.
#
# WHY KEYLESS, DELIBERATELY
# -------------------------
# /v1/link-check answers from RelayShield's IOC corpus, Google Safe Browsing's
# free tier and RDAP. No paid upstream, so there is no bill to protect and the
# per-IP daily cap in the Lambda (KEYLESS_IP_DAILY_CAP) is the whole guardrail.
# API Key Required stays FALSE here, unlike the billed endpoints in step 2b of
# that runbook. An integration that needs a signup before its first response is
# not a one-line integration, and the widget's entire premise is that first call.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
PARENT_PATH=/v1
PART=link-check
FUNC=relayshield-api

export AWS_PAGER=""

aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT. Nothing changed." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 2. Does the Lambda actually route $PARENT_PATH/$PART?"
# Checked against the repo rather than assumed, because creating a gateway route
# to a path the handler does not know returns a confusing 404 body from our own
# code instead of a clear error.
if grep -q "\"$PARENT_PATH/$PART\"" relayshield_api.py; then
  echo "   yes -- \"$PARENT_PATH/$PART\" is in relayshield_api.py"
else
  echo "STOP: relayshield_api.py has no route for $PARENT_PATH/$PART." >&2
  echo "Deploy the handler first; the gateway would forward to a 404." >&2
  exit 1
fi
echo

echo "== 3. Find the $PARENT_PATH resource on API $API_ID"
PARENT_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
              --query "items[?path=='$PARENT_PATH'].id | [0]" --output text)
if [ -z "$PARENT_ID" ] || [ "$PARENT_ID" = "None" ]; then
  echo "STOP: no $PARENT_PATH resource on API $API_ID. Wrong API id?" >&2
  exit 1
fi
echo "   $PARENT_PATH -> $PARENT_ID"

RES_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
           --query "items[?path=='$PARENT_PATH/$PART'].id | [0]" --output text)
if [ -n "$RES_ID" ] && [ "$RES_ID" != "None" ]; then
  echo "   $PARENT_PATH/$PART already exists -> $RES_ID"
else
  RES_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
             --parent-id "$PARENT_ID" --path-part "$PART" \
             --query 'id' --output text)
  echo "   created $PARENT_PATH/$PART -> $RES_ID"
fi
echo

echo "== 4. POST method, no API key"
if aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
     --http-method POST >/dev/null 2>&1; then
  echo "   POST already exists -- leaving it alone"
else
  aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
    --http-method POST --authorization-type NONE --no-api-key-required \
    --query 'httpMethod' --output text
  echo "   POST created (authorization NONE, api key NOT required)"

  LAMBDA_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"
  aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$RES_ID" \
    --http-method POST --type AWS_PROXY --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" \
    --query 'type' --output text
  echo "   integration -> $FUNC (AWS_PROXY)"

  # Idempotent by construction: a fixed statement id means a re-run collides
  # with itself rather than stacking duplicate permissions.
  aws lambda add-permission --function-name "$FUNC" \
    --statement-id "apigw-$PART" --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/POST$PARENT_PATH/$PART" \
    --query 'Statement' --output text >/dev/null 2>&1 \
    && echo "   lambda invoke permission added" \
    || echo "   lambda invoke permission already present"
fi
echo

echo "== 5. Deploy the $STAGE stage"
# A gateway change is invisible until the stage is redeployed. Forgetting this
# leaves the endpoint 403 while every console page shows it configured.
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --description "add $PARENT_PATH/$PART (keyless link check for the Telegram widget)" \
  --query 'id' --output text
echo

echo "== 6. Prove it end to end"
URL="https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE$PARENT_PATH/$PART"
echo "   POST $URL"
BODY=$(curl -sS -X POST "$URL" \
         -H 'Content-Type: application/json' \
         -d '{"url":"https://example.com","source":"setup-script"}' || true)
echo "   $BODY"
echo
case "$BODY" in
  *'"ok": true'*|*'"ok":true'*)
    echo "LIVE. The widget's link check now works with no key:"
    echo "  curl -sS -X POST $URL -H 'Content-Type: application/json' -d '{\"url\":\"https://example.com\"}'"
    ;;
  *"Missing Authentication Token"*)
    echo "STOP: the gateway still does not know this path. Re-run; if it persists," >&2
    echo "check that step 5 deployed the $STAGE stage." >&2
    exit 1
    ;;
  *"Forbidden"*)
    echo "STOP: 403. API Key Required is probably still true on the POST method." >&2
    exit 1
    ;;
  *)
    echo "STOP: unexpected response. The route exists but the handler did not" >&2
    echo "answer as expected -- has relayshield-api been deployed since the" >&2
    echo "endpoint was added to ROUTES?" >&2
    exit 1
    ;;
esac
