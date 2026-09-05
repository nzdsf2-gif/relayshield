#!/bin/sh
# Create the relayshield-mpp-settlement Lambda, its own IAM role, and its two
# API Gateway routes. Then prove the endpoint answers.
#
#   sh tools/create_mpp_settlement_lambda.sh
#
# Run from the repo root, on the Mac. Idempotent: every step checks for what it
# is about to create and skips it, so a re-run after a failure is safe.
#
# WHY A DEDICATED ROLE
# --------------------
# CLAUDE.md, "IAM -- one role per Lambda". relayshield-breach-check-role-1sapnwdl
# carries 26 inline policies at 10,127 of a hard 10,240-byte budget AND 10 of 10
# managed slots. There is no room on it, and reaching for it is what filled it.
# This function needs four permissions, so it gets its own role with exactly
# those four and nothing else.
#
# WHY THE FUNCTION IS NOT IN deploy_lambdas.yml YET
# --------------------------------------------------
# The deployer calls update-function-code on whatever LAMBDA_MAP names. Mapping a
# function that does not exist turns the first push red with a
# ResourceNotFoundException that looks like a code failure and is not. So this
# script creates the function FIRST, and the last thing it prints is the mapping
# step to take once it exists.
#
# THE RAIL STARTS PINNED TO THE FACILITATOR, DELIBERATELY
# --------------------------------------------------------
# Stripe crypto reads Ineligible on this account. RELAYSHIELD_MPP_RAIL=facilitator
# means the endpoint never calls Stripe at all, so it is live and collecting on
# the rail that already works while the access request is outstanding. Flip it to
# "auto" only after tools/mpp_settlement_selftest.py returns 200s.
#
# RELAYSHIELD_MPP_CHALLENGE=off for a separate reason, and do not flip the two
# together: we can ISSUE a compliant MPP challenge but cannot yet REDEEM a
# Shared Payment Token credential. Advertising a payment method we would then
# reject spends an agent's authorisation on a route that cannot complete.
#
# RELAYSHIELD_API_BASE_URL is the BRANDED host, not the execute-api one. That URL
# is advertised as the resource in every 402 and is what x402 indexers persist,
# so a raw AWS hostname pins callers to something that breaks if the gateway id
# changes -- the same reasoning as the live agentic-api handler's own comment.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-mpp-settlement
ROLE=relayshield-mpp-settlement-role
SOURCE_FUNC=relayshield-agentic-api      # where the wallet env var is copied from
RUNTIME=python3.12

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

echo "== 2. Sources present, and the tests pass"
for F in relayshield_mpp_settlement.py relayshield_agentic_api.py; do
  [ -f "$F" ] || { echo "STOP: $F missing. Run from the repo root." >&2; exit 1; }
done
python3 test_mpp_settlement.py >/dev/null 2>&1 \
  && echo "   test_mpp_settlement.py passes" \
  || { echo "STOP: test_mpp_settlement.py fails. Fix that before creating anything." >&2; exit 1; }
echo

echo "== 3. The dedicated role"
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  echo "   $ROLE already exists"
else
  aws iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},
                    "Action":"sts:AssumeRole"}]}' \
    --description "Dedicated role for the MPP settlement endpoint. Four permissions, no more." \
    --query 'Role.RoleName' --output text
  echo "   created $ROLE"
fi

# Rewritten every run rather than created once: put-role-policy is idempotent,
# and a policy that drifts from this file is the exact failure the DRIFT RULE is
# about. What is in this script is what is on the role.
aws iam put-role-policy --role-name "$ROLE" --policy-name relayshield-mpp-settlement \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Sid\":\"Logs\",\"Effect\":\"Allow\",
       \"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],
       \"Resource\":\"arn:aws:logs:$REGION:$ACCOUNT:*\"},
      {\"Sid\":\"ReadIocCorpus\",\"Effect\":\"Allow\",
       \"Action\":[\"dynamodb:Query\",\"dynamodb:GetItem\"],
       \"Resource\":\"arn:aws:dynamodb:$REGION:$ACCOUNT:table/relayshield_intel_iocs\"},
      {\"Sid\":\"WriteSettlements\",\"Effect\":\"Allow\",
       \"Action\":[\"dynamodb:PutItem\"],
       \"Resource\":\"arn:aws:dynamodb:$REGION:$ACCOUNT:table/relayshield_payg_settlements\"},
      {\"Sid\":\"ReadStripeKey\",\"Effect\":\"Allow\",
       \"Action\":[\"secretsmanager:GetSecretValue\"],
       \"Resource\":\"arn:aws:secretsmanager:$REGION:$ACCOUNT:secret:relayshield/stripe_secret_key*\"}
    ]}"
echo "   inline policy relayshield-mpp-settlement written (4 statements)"
echo

echo "== 4. Package"
rm -f /tmp/mpp_deploy.zip
zip -j -q /tmp/mpp_deploy.zip relayshield_mpp_settlement.py relayshield_agentic_api.py
echo "   relayshield_mpp_settlement.py + relayshield_agentic_api.py"
echo "   (the detector is packaged rather than re-implemented -- this repo already"
echo "    carries four copies of one pattern table and does not need a fifth)"
echo

echo "== 5. The function"
# Read the wallet from the function that is already using it rather than pasting
# it in. --query pulls the one value; printing the whole environment block is how
# every secret in it ends up in a terminal scrollback.
WALLET=$(aws lambda get-function-configuration --function-name "$SOURCE_FUNC" \
           --query 'Environment.Variables.RELAYSHIELD_X402_WALLET' --output text 2>/dev/null || echo "None")
if [ "$WALLET" = "None" ] || [ -z "$WALLET" ]; then
  echo "STOP: could not read RELAYSHIELD_X402_WALLET from $SOURCE_FUNC." >&2
  echo "Without it the fallback rail has nowhere to send money and the endpoint 503s." >&2
  exit 1
fi
echo "   wallet read from $SOURCE_FUNC (value not printed)"

if aws lambda get-function --function-name "$FUNC" >/dev/null 2>&1; then
  echo "   $FUNC exists -- updating code only, leaving configuration alone"
  aws lambda update-function-code --function-name "$FUNC" \
    --zip-file fileb:///tmp/mpp_deploy.zip --query 'FunctionName' --output text
  aws lambda wait function-updated --function-name "$FUNC"
else
  # IAM is eventually consistent, and a role created seconds ago is routinely
  # not yet assumable: CreateFunction fails with
  #   InvalidParameterValueException: The role defined for the function cannot
  #   be assumed by Lambda
  # which reads like a broken trust policy and is a race. Retry rather than
  # making the operator re-run and wonder which it was. Seen 2026-09-05.
  ATTEMPT=1
  until aws lambda create-function --function-name "$FUNC" \
    --runtime "$RUNTIME" \
    --role "arn:aws:iam::$ACCOUNT:role/$ROLE" \
    --handler relayshield_mpp_settlement.lambda_handler \
    --zip-file fileb:///tmp/mpp_deploy.zip \
    --timeout 30 --memory-size 256 \
    --description "MPP settlement endpoint -- machine payments on Stripe's rail" \
    --environment "Variables={RELAYSHIELD_MPP_RAIL=facilitator,RELAYSHIELD_MPP_NETWORK=base,RELAYSHIELD_MPP_CHALLENGE=off,RELAYSHIELD_X402_WALLET=$WALLET,RELAYSHIELD_API_BASE_URL=https://api.relayshield.net}" \
    --query 'FunctionName' --output text
  do
    if [ "$ATTEMPT" -ge 6 ]; then
      echo "STOP: still cannot create $FUNC after $ATTEMPT attempts." >&2
      echo "If the error is 'cannot be assumed by Lambda' this stopped being a" >&2
      echo "race a minute ago -- check the role's trust policy names" >&2
      echo "lambda.amazonaws.com. Any other error is not a race at all." >&2
      exit 1
    fi
    echo "   attempt $ATTEMPT failed (IAM is eventually consistent); waiting 10s"
    ATTEMPT=$((ATTEMPT + 1))
    sleep 10
  done
  aws lambda wait function-active --function-name "$FUNC"
  echo "   created $FUNC (rail pinned to facilitator -- see the header of this script)"
fi
rm -f /tmp/mpp_deploy.zip
echo

echo "== 6. API Gateway routes"
V1_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
          --query "items[?path=='/v1'].id | [0]" --output text)
if [ -z "$V1_ID" ] || [ "$V1_ID" = "None" ]; then
  echo "STOP: no /v1 resource on API $API_ID. Wrong API id?" >&2
  exit 1
fi

LAMBDA_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"

resource_id() {   # $1 = full path, $2 = parent id, $3 = path part
  ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
         --query "items[?path=='$1'].id | [0]" --output text)
  if [ -z "$ID" ] || [ "$ID" = "None" ]; then
    ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
           --parent-id "$2" --path-part "$3" --query 'id' --output text)
    echo "   created $1 -> $ID" >&2
  else
    echo "   $1 already exists -> $ID" >&2
  fi
  echo "$ID"
}

wire() {          # $1 = resource id, $2 = method, $3 = full path, $4 = statement suffix
  if aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$1" \
       --http-method "$2" >/dev/null 2>&1; then
    echo "   $2 $3 already wired -- leaving it alone"
    return
  fi
  aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$1" \
    --http-method "$2" --authorization-type NONE --no-api-key-required \
    --query 'httpMethod' --output text >/dev/null
  aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$1" \
    --http-method "$2" --type AWS_PROXY --integration-http-method POST \
    --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" \
    --query 'type' --output text >/dev/null
  # Fixed statement id, so a re-run collides with itself instead of stacking
  # duplicate permissions on the function.
  aws lambda add-permission --function-name "$FUNC" \
    --statement-id "apigw-$4" --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/$2$3" \
    --query 'Statement' --output text >/dev/null 2>&1 || true

  # VERIFY, rather than assert the call we just made returned 200. Reporting
  # "wired to relayshield-mpp-settlement" over an integration that names some
  # other function is the same defect as reporting LIVE over a 402 that quoted
  # the wrong price: the step asserted its own action and never read the result.
  # Cost one failed run on 2026-09-05, where both routes reported wired and
  # relayshield-api answered both.
  GOT_URI=$(aws apigateway get-integration --rest-api-id "$API_ID" \
              --resource-id "$1" --http-method "$2" --query 'uri' --output text 2>/dev/null || echo "")
  GOT=$(printf '%s' "$GOT_URI" | sed -n 's#.*:function:\([^/]*\)/invocations#\1#p')
  if [ "$GOT" != "$FUNC" ]; then
    echo "STOP: $2 $3 integration points at '${GOT:-nothing}', not $FUNC." >&2
    echo "Nothing further will work. sh tools/diagnose_mpp_routes.sh" >&2
    exit 1
  fi
  echo "   $2 $3 -> $FUNC (integration read back and confirmed)"
}

# No API key on either route. An agent that discovers the endpoint has to be
# able to hit it and get a 402, which IS the paywall -- requiring a signup before
# the challenge defeats the entire point of a machine-payable endpoint.
MPP_ID=$(resource_id "/v1/mpp" "$V1_ID" "mpp")
wire "$MPP_ID" GET "/v1/mpp" "mpp-descriptor"

RISK_ID=$(resource_id "/v1/mpp/mcp-registry-risk" "$MPP_ID" "mcp-registry-risk")
wire "$RISK_ID" POST "/v1/mpp/mcp-registry-risk" "mpp-registry-risk"
echo

echo "== 7. Deploy the $STAGE stage"
# A gateway change is invisible until the stage is redeployed. Skipping this
# leaves both routes 403 while every console page shows them configured.
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --description "add /v1/mpp and /v1/mpp/mcp-registry-risk (MPP settlement endpoint)" \
  --query 'id' --output text
echo

echo "== 8. Prove it end to end"
BASE="https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE"

echo "   GET $BASE/v1/mpp"
DESC=$(curl -sS "$BASE/v1/mpp" || true)
echo "   $DESC"
echo

echo "   POST $BASE/v1/mpp/mcp-registry-risk  (no payment -- expecting 402)"
CODE=$(curl -sS -o /tmp/mpp_402.json -w '%{http_code}' \
         -X POST "$BASE/v1/mpp/mcp-registry-risk" \
         -H 'Content-Type: application/json' \
         -d '{"server_url":"https://modelcontextprotoco1.io"}' || true)
echo "   HTTP $CODE"
head -c 600 /tmp/mpp_402.json; echo; echo

case "$CODE" in
  402)
    echo "LIVE. The endpoint challenges for payment."
    echo
    echo "NEXT, in this order:"
    echo "  1. AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py"
    echo "     -- settles whether the Stripe parameter shapes are right, and prints the"
    echo "        exact text to send machine-payments@stripe.com if the account is not"
    echo "        enabled."
    echo "  2. Only once that returns 200s:"
    echo "     AWS_PROFILE=relayshield aws lambda update-function-configuration \\"
    echo "       --function-name $FUNC --region $REGION --no-cli-pager \\"
    echo "       --environment 'Variables={RELAYSHIELD_MPP_RAIL=auto,...}'"
    echo "     (re-send every variable -- update-function-configuration REPLACES the"
    echo "      environment block, it does not merge into it)"
    echo "  3. Map it for CI, now that the function exists:"
    echo "       [\"relayshield_mpp_settlement.py\"]=\"$FUNC\"   in deploy_lambdas.yml"
    echo "       and the same name in lambda_drift_check.yml"
    echo "     then: python3 test_workflows_parse.py"
    echo "     ($FUNC is already in iam_github_deploy_invoke.json, so the first CI"
    echo "      deploy will not repeat run 134's denied import probe.)"
    ;;
  403)
    echo "STOP: 403. Either the stage did not redeploy, or a method still requires" >&2
    echo "an API key. Re-run; if it persists, check step 7." >&2
    exit 1
    ;;
  503)
    echo "STOP: 503 means no usable payTo. RELAYSHIELD_X402_WALLET did not reach the" >&2
    echo "function. Check its environment." >&2
    exit 1
    ;;
  *)
    echo "STOP: expected 402, got $CODE." >&2
    echo >&2
    echo "READ THE BODY ABOVE BEFORE THE LOG. It names the responder:" >&2
    echo "  \"unknown endpoint: ...\"  is relayshield_api.py, which is NOT in this" >&2
    echo "      package. A different Lambda answered and the routing is wrong." >&2
    echo "  \"Not found\"              is THIS handler, so the route is right and" >&2
    echo "      the path it matched on is not MPP_PATH." >&2
    echo >&2
    echo "Either way the next step is the same, and it is read-only:" >&2
    echo "  sh tools/diagnose_mpp_routes.sh" >&2
    exit 1
    ;;
esac
