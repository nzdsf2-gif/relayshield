#!/bin/sh
# Create the relayshield-mcp-http Lambda, its own IAM role, and the /mcp route on
# the existing API Gateway. Then prove the endpoint answers the MCP handshake.
#
#   sh tools/create_mcp_http_lambda.sh
#
# Run from the repo root, on the Mac. Idempotent: every step checks for what it
# is about to create and skips it, so a re-run after a failure is safe.
#
# WHY THIS EXISTS (2026-10-25)
# ----------------------------
# The AWS Foundational Technical Review is Blocked on "AWS Marketplace product is
# deployed on AWS" for prod-kkvurtspreofy, whose registered MCP endpoint is a
# Hugging Face Space. relayshield_mcp_http.py serves the same 13 tools from AWS,
# at https://api.relayshield.net/mcp. Creating it changes NOTHING live: the
# Hugging Face Spaces keep running and the listing still points at the Space until
# a separate, deliberate listing change set moves it.
#
# WHY A DEDICATED ROLE
# --------------------
# CLAUDE.md, "IAM -- one role per Lambda". This function touches no AWS service:
# it only makes outbound HTTPS calls to api.relayshield.net. So its role carries
# CloudWatch Logs and nothing else. Not DynamoDB, not Secrets Manager.
#
# WHY THE FUNCTION IS NOT IN deploy_lambdas.yml YET
# -------------------------------------------------
# The deployer calls update-function-code on whatever LAMBDA_MAP names, so mapping
# a function that does not exist turns the first push red with a
# ResourceNotFoundException that reads like a code failure. This script creates
# the function FIRST; the last thing it prints is the mapping to add afterwards.
#
# THE DEMO KEY IS NOT COPIED INTO A SECOND SOURCE FILE
# ----------------------------------------------------
# check_llm_credential_exposure has a zero-key free tier that uses a shared demo
# key. app.py holds it; this reads it from there at run time and sets it as the
# function's RS_DEMO_API_KEY. The value is never printed.
#
# UNVERIFIED FROM THE CONTAINER: this container has no AWS credentials and no aws
# CLI, so nothing below that talks to AWS has been run. The Python it packages has
# (test_relayshield_mcp_http.py, including real sockets). The first run is the
# first test of the AWS half; every step prints what it did and STOPs on a surprise.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
API_ID=atq6wtkp6k
STAGE=prod
FUNC=relayshield-mcp-http
ROLE=relayshield-mcp-http-role
RUNTIME=python3.12
BRANDED=https://api.relayshield.net

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
for F in relayshield_mcp_http.py hf-space-mcp-server/app.py test_relayshield_mcp_http.py; do
  [ -f "$F" ] || { echo "STOP: $F missing. Run from the repo root." >&2; exit 1; }
done
python3 test_relayshield_mcp_http.py >/dev/null 2>&1 \
  && echo "   test_relayshield_mcp_http.py passes" \
  || { echo "STOP: test_relayshield_mcp_http.py fails. Fix that before creating anything." >&2; exit 1; }
DEMO_KEY=$(sed -n 's/^_DEMO_API_KEY = "\(rs_live_[0-9a-f]*\)".*/\1/p' hf-space-mcp-server/app.py)
if [ -z "$DEMO_KEY" ]; then
  echo "STOP: could not read _DEMO_API_KEY from hf-space-mcp-server/app.py." >&2
  echo "Without it the free tool would ask every caller for a key. Nothing changed." >&2
  exit 1
fi
echo "   demo key read from app.py (value not printed)"
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
    --description "Dedicated role for the AWS-hosted MCP endpoint. CloudWatch Logs only." \
    --query 'Role.RoleName' --output text
  echo "   created $ROLE"
fi
# Rewritten every run: what is in this script is what is on the role.
aws iam put-role-policy --role-name "$ROLE" --policy-name relayshield-mcp-http \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Sid\":\"Logs\",\"Effect\":\"Allow\",
       \"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],
       \"Resource\":\"arn:aws:logs:$REGION:$ACCOUNT:*\"}
    ]}"
echo "   inline policy relayshield-mcp-http written (1 statement: logs)"
echo

echo "== 4. Package"
rm -f /tmp/mcp_http_deploy.zip
zip -j -q /tmp/mcp_http_deploy.zip relayshield_mcp_http.py
echo "   relayshield_mcp_http.py (standard library only, nothing else to bundle)"
echo

echo "== 5. The function"
if aws lambda get-function --function-name "$FUNC" >/dev/null 2>&1; then
  echo "   $FUNC exists -- updating code only, leaving configuration alone"
  aws lambda update-function-code --function-name "$FUNC" \
    --zip-file fileb:///tmp/mcp_http_deploy.zip --query 'FunctionName' --output text
  aws lambda wait function-updated --function-name "$FUNC"
else
  # A role created seconds ago is routinely not yet assumable; retry rather than
  # make the operator wonder whether the trust policy is wrong. Seen 2026-09-05.
  ATTEMPT=1
  until aws lambda create-function --function-name "$FUNC" \
    --runtime "$RUNTIME" \
    --role "arn:aws:iam::$ACCOUNT:role/$ROLE" \
    --handler relayshield_mcp_http.lambda_handler \
    --zip-file fileb:///tmp/mcp_http_deploy.zip \
    --timeout 60 --memory-size 256 \
    --description "MCP server (Streamable HTTP) for the Consumption Security bundles, hosted on AWS" \
    --environment "Variables={RS_DEMO_API_KEY=$DEMO_KEY}" \
    --query 'FunctionName' --output text
  do
    if [ "$ATTEMPT" -ge 6 ]; then
      echo "STOP: still cannot create $FUNC after $ATTEMPT attempts." >&2
      echo "If the error is 'cannot be assumed by Lambda' this stopped being a" >&2
      echo "race a minute ago -- check the role's trust policy names lambda.amazonaws.com." >&2
      exit 1
    fi
    echo "   attempt $ATTEMPT failed (IAM is eventually consistent); waiting 10s"
    ATTEMPT=$((ATTEMPT + 1))
    sleep 10
  done
  aws lambda wait function-active --function-name "$FUNC"
  echo "   created $FUNC"
fi
rm -f /tmp/mcp_http_deploy.zip
echo

echo "== 6. API Gateway route /mcp"
ROOT_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
            --query "items[?path=='/'].id | [0]" --output text)
if [ -z "$ROOT_ID" ] || [ "$ROOT_ID" = "None" ]; then
  echo "STOP: no root resource on API $API_ID. Wrong API id?" >&2
  exit 1
fi

LAMBDA_ARN="arn:aws:lambda:$REGION:$ACCOUNT:function:$FUNC"

MCP_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
           --query "items[?path=='/mcp'].id | [0]" --output text)
if [ -z "$MCP_ID" ] || [ "$MCP_ID" = "None" ]; then
  MCP_ID=$(aws apigateway create-resource --rest-api-id "$API_ID" \
             --parent-id "$ROOT_ID" --path-part mcp --query 'id' --output text)
  echo "   created /mcp -> $MCP_ID"
else
  echo "   /mcp already exists -> $MCP_ID"
fi

wire() {          # $1 = method
  if aws apigateway get-method --rest-api-id "$API_ID" --resource-id "$MCP_ID" \
       --http-method "$1" >/dev/null 2>&1; then
    echo "   $1 /mcp already wired -- leaving it alone"
  else
    aws apigateway put-method --rest-api-id "$API_ID" --resource-id "$MCP_ID" \
      --http-method "$1" --authorization-type NONE --no-api-key-required \
      --query 'httpMethod' --output text >/dev/null
    aws apigateway put-integration --rest-api-id "$API_ID" --resource-id "$MCP_ID" \
      --http-method "$1" --type AWS_PROXY --integration-http-method POST \
      --uri "arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations" \
      --query 'type' --output text >/dev/null
    aws lambda add-permission --function-name "$FUNC" \
      --statement-id "apigw-mcp-$1" --action lambda:InvokeFunction \
      --principal apigateway.amazonaws.com \
      --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*/$1/mcp" \
      --query 'Statement' --output text >/dev/null 2>&1 || true
  fi
  # Verify by reading back, not by trusting the call just made.
  GOT_URI=$(aws apigateway get-integration --rest-api-id "$API_ID" \
              --resource-id "$MCP_ID" --http-method "$1" --query 'uri' --output text 2>/dev/null || echo "")
  GOT_FN=$(printf '%s' "$GOT_URI" | sed -n 's#.*:function:\([^/]*\)/invocations#\1#p')
  if [ "$GOT_FN" != "$FUNC" ]; then
    echo "STOP: $1 /mcp integration points at '${GOT_FN:-nothing}', not $FUNC." >&2
    exit 1
  fi
  echo "   $1 /mcp -> $FUNC (integration read back and confirmed)"
}

# No API key on the route: an MCP client has to be able to handshake and list
# tools before it has any key. Each tool call is authenticated by the key the
# CALLER passes, exactly as on the Space; the backend rejects a bad one.
wire POST
wire GET
wire OPTIONS
echo

echo "== 7. Deploy the $STAGE stage"
aws apigateway create-deployment --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --description "add /mcp (AWS-hosted MCP server)" --query 'id' --output text
echo

echo "== 8. Prove it end to end"
. "$(dirname "$0")/lib_await_route.sh"

PROBE_INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
PROBE_LIST='{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

for BASE in "https://$API_ID.execute-api.$REGION.amazonaws.com/$STAGE" "$BRANDED"; do
  echo "   POST $BASE/mcp  (initialize)"
  if ! await_http 200 -X POST "$BASE/mcp" -H 'Content-Type: application/json' -d "$PROBE_INIT"; then
    echo "STOP: expected 200 from $BASE/mcp, got $AWAIT_STATUS." >&2
    echo "READ THE BODY BEFORE THE LOG:" >&2
    head -c 600 "$AWAIT_BODY" >&2; echo >&2
    echo "  {\"message\":\"Missing Authentication Token\"}  the route is not on this host/stage." >&2
    echo "  {\"error\":...} or an unknown-endpoint body     a different Lambda answered." >&2
    echo "  403 or 404 that persists                         stage not redeployed, or" >&2
    echo "                                                   $BRANDED is mapped to another API." >&2
    exit 1
  fi
  head -c 300 "$AWAIT_BODY"; echo

  COUNT=$(curl -sS -X POST "$BASE/mcp" -H 'Content-Type: application/json' -d "$PROBE_LIST" \
            | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["result"]["tools"]))' 2>/dev/null || echo 0)
  echo "   tools/list -> $COUNT tools"
  if [ "$COUNT" != "13" ]; then
    echo "STOP: expected 13 tools from $BASE/mcp, got $COUNT." >&2
    exit 1
  fi
done
echo

echo "LIVE at $BRANDED/mcp (13 tools). The listing still points at the Hugging Face Space."
echo
echo "NEXT, in this order:"
echo "  1. Map it for CI, now that the function exists:"
echo "       [\"relayshield_mcp_http.py\"]=\"$FUNC\"   in deploy_lambdas.yml and lambda_drift_check.yml,"
echo "       and the function ARN in iam_github_deploy_invoke.json; then python3 test_workflows_parse.py"
echo "  2. Try a real tool call from an MCP client against $BRANDED/mcp with your own key."
echo "  3. Only then: the listing change set that moves Bundle D's registered MCP endpoint."
echo "     That is a change set on a LIVE product and has its own guarded step."
