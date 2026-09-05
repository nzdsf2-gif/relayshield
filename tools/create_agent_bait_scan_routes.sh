#!/bin/sh
# Expose agent-bait-scan on both doors, x402 first, and prove each answers.
#
#   sh tools/create_agent_bait_scan_routes.sh
#
# Run from the repo root, on the Mac. Idempotent: every step checks for what it
# is about to create and skips it, so a re-run after a failure is safe.
#
# TWO DOORS, IN THIS ORDER, ON PURPOSE
# ------------------------------------
#   POST /v1/payg/agent-bait-scan       x402, no key, no signup   -- first
#   POST /v1/metered/agent-bait-scan    API key, $0.50/call       -- second
#
# The x402 door is the one an agent actually arrives at, it needs no signup, and
# it has no gate in front of it. The metered door is the same handler for
# API-key callers.
#
# THE AWS BUNDLE D DIMENSION IS NOT HERE, AND THAT IS DELIBERATE.
# Adding a third usage dimension to a PUBLISHED Marketplace product is a change
# set against the listing with AWS's review latency on their side of it. It goes
# in once the endpoint has run against real traffic long enough to have a
# measured false-positive rate -- a change set is a bad place to discover a
# fresh heuristic needs tuning. Tracked for the next session in TODO.md.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-agentic-api

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

echo "== 2. Does the Lambda actually route these paths?"
# Checked against the repo rather than assumed: a gateway route to a path the
# handler does not know returns a confusing 404 from our own code.
for P in "/v1/payg/agent-bait-scan" "/v1/metered/agent-bait-scan"; do
  if grep -q "\"$P\"" relayshield_agentic_api.py; then
    echo "   yes -- $P is routed"
  else
    echo "STOP: relayshield_agentic_api.py has no route for $P." >&2
    exit 1
  fi
done
python3 test_agent_bait_scan.py >/dev/null 2>&1 \
  && echo "   test_agent_bait_scan.py passes" \
  || { echo "STOP: test_agent_bait_scan.py fails. Fix that first." >&2; exit 1; }
echo

echo "== 3. Has the handler actually been deployed since agent-bait-scan was added?"
# The trap that nearly wasted the Discord fix in reverse: a gateway route to a
# handler whose LIVE copy predates the endpoint returns 404 from our own code,
# which reads exactly like a broken route and is not.
LAST=$(aws lambda get-function-configuration --function-name "$FUNC" \
         --query 'LastModified' --output text)
echo "   $FUNC last modified $LAST"
echo "   If that predates the merge that added agent-bait-scan, STOP and let the"
echo "   deploy workflow run first. relayshield_agentic_api.py is in LAMBDA_MAP"
echo "   as of 2026-09-04, so a push touching it deploys automatically."
echo

LAMBDA_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"

wire() {   # $1 = parent path, $2 = path part, $3 = api-key required (true|false)
  PARENT_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
                --query "items[?path=='$1'].id | [0]" --output text)
  if [ -z "$PARENT_ID" ] || [ "$PARENT_ID" = "None" ]; then
    echo "STOP: no $1 resource on API $API_ID." >&2
    exit 1
  fi
  FULL="$1/$2"
  RES_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
             --query "items[?path=='$FULL'].id | [0]" --output text)
  if [ -z "$RES_ID" ] || [ "$RES_ID" = "None" ]; then
    RES_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
               --parent-id "$PARENT_ID" --path-part "$2" --query 'id' --output text)
    echo "   created $FULL -> $RES_ID"
  else
    echo "   $FULL already exists -> $RES_ID"
  fi

  if aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
       --http-method POST >/dev/null 2>&1; then
    echo "   POST $FULL already wired -- leaving it alone"
    return
  fi
  if [ "$3" = "true" ]; then
    aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
      --http-method POST --authorization-type NONE --api-key-required \
      --query 'httpMethod' --output text >/dev/null
  else
    aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$RES_ID" \
      --http-method POST --authorization-type NONE --no-api-key-required \
      --query 'httpMethod' --output text >/dev/null
  fi
  aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$RES_ID" \
    --http-method POST --type AWS_PROXY --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" \
    --query 'type' --output text >/dev/null
  aws lambda add-permission --function-name "$FUNC" \
    --statement-id "apigw-$(echo "$FULL" | tr '/' '-' | cut -c2-60)" \
    --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/POST$FULL" \
    --query 'Statement' --output text >/dev/null 2>&1 || true
  echo "   POST $FULL wired (api key required: $3)"
}

echo "== 4. The x402 door, keyless"
# Keyless because the 402 IS the paywall. Requiring a signup before an agent can
# even receive the payment challenge defeats the point of a machine-payable
# endpoint, and it is how every other /v1/payg/ route already works.
wire "/v1/payg" "agent-bait-scan" false
echo

echo "== 5. The metered door, API key required"
wire "/v1/metered" "agent-bait-scan" true
echo

echo "== 6. Deploy the $STAGE stage"
# A gateway change is invisible until the stage is redeployed. Skipping this
# leaves both routes 403 while every console page shows them configured.
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --description "add agent-bait-scan on both doors" \
  --query 'id' --output text
echo

echo "== 7. Prove both doors"
BASE="https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE"

echo "   POST $BASE/v1/payg/agent-bait-scan  (no payment -- expecting 402)"
CODE=$(curl -sS -o /tmp/abs_payg.json -w '%{http_code}' \
         -X POST "$BASE/v1/payg/agent-bait-scan" \
         -H 'Content-Type: application/json' \
         -d '{"repository":"nzdsf2-gif/relayshield"}' || true)
echo "   HTTP $CODE"
head -c 400 /tmp/abs_payg.json; echo; echo

echo "   POST $BASE/v1/metered/agent-bait-scan  (no key -- expecting 403)"
MCODE=$(curl -sS -o /tmp/abs_metered.json -w '%{http_code}' \
          -X POST "$BASE/v1/metered/agent-bait-scan" \
          -H 'Content-Type: application/json' -d '{}' || true)
echo "   HTTP $MCODE"
echo

case "$CODE" in
  402)
    echo "LIVE. The x402 door challenges for payment at \$0.50."
    echo
    echo "NEXT:"
    echo "  1. Register a ?source= key for it if it gets its own landing link."
    echo "  2. Bundle D dimension: NEXT SESSION, see TODO.md. It is an AWS change"
    echo "     set and it waits on a measured false-positive rate."
    echo "  3. Blog post: publish only AFTER this returns 402 in public, per the"
    echo "     XSOAR rule. Do not quote Island's numbers as ours."
    ;;
  404)
    echo "STOP: 404 from our own handler means the LIVE Lambda predates" >&2
    echo "agent-bait-scan. The route is fine; the code is old. Let the deploy" >&2
    echo "workflow run, then re-run step 7 only." >&2
    exit 1
    ;;
  403)
    echo "STOP: 403. Either the stage did not redeploy, or API Key Required is" >&2
    echo "set on the PAYG method. It must not be." >&2
    exit 1
    ;;
  *)
    echo "STOP: expected 402, got $CODE. Read the body above." >&2
    exit 1
    ;;
esac
