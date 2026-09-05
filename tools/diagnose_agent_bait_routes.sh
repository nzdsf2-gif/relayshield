#!/bin/sh
# Which Lambda actually answers /v1/payg/agent-bait-scan? Read-only.
#
#   sh tools/diagnose_agent_bait_routes.sh
#
# WHY THIS EXISTS
# ---------------
# The first run of create_agent_bait_scan_routes.sh reported "LIVE" on a 402
# that quoted $0.25. That is relayshield-api's default price for an unknown
# /v1/payg path; this endpoint's is $0.50. So a well-formed 402 came back from
# a Lambda that has never heard of agent-bait-scan, and the script called it
# success because it asserted the status code and ignored the body.
#
# Two candidate causes with different fixes, and guessing between them is how
# this repo has wasted days before:
#   A. the gateway resource is integrated with the wrong function
#   B. the route is right and relayshield-agentic-api simply has not been
#      deployed since agent-bait-scan was added, so it 404s and something else
#      answers
#
# This asks both questions directly instead. Every command is a read.

set -eu

PROFILE=relayshield
REGION=us-east-1
API_ID=atq6wtkp6k
STAGE=prod

export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Account"
aws sts get-caller-identity --query Account --output text
echo

echo "== 2. Every gateway resource whose path mentions payg, metered or bait"
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'payg') || contains(path,'metered') || contains(path,'bait')].[id,path]" \
  --output text | sort -k2 | head -60
echo

echo "== 3. Which function is each agent-bait-scan route integrated with?"
# The decisive question. The integration URI carries the target ARN.
for P in "/v1/payg/agent-bait-scan" "/v1/metered/agent-bait-scan"; do
  RID=$(aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
          --query "items[?path=='$P'].id | [0]" --output text)
  if [ -z "$RID" ] || [ "$RID" = "None" ]; then
    echo "   $P -- NO RESOURCE"
    continue
  fi
  URI=$(aws apigateway get-integration --rest-api-id "$API_ID" --resource-id "$RID" \
          --http-method POST --query 'uri' --output text 2>/dev/null || echo "(no POST integration)")
  echo "   $P  ($RID)"
  echo "     -> $URI"
done
echo

echo "== 4. Is anything shadowing them? A greedy proxy under /v1 or /v1/payg"
aws apigateway get-resources --rest-api-id "$API_ID" --limit 500 \
  --query "items[?contains(path,'{proxy')].[id,path]" --output text || true
echo "   (an explicit resource beats {proxy+}, so a hit here is context, not a cause)"
echo

echo "== 5. What does each Lambda say ITSELF, with the gateway taken out of it?"
# This separates cause A from cause B completely: invoke the function directly.
for FN in relayshield-agentic-api relayshield-api; do
  echo "   --- $FN ---"
  aws lambda get-function-configuration --function-name "$FN" \
    --query '[LastModified,Runtime,CodeSize]' --output text 2>/dev/null || {
      echo "     not readable"; continue; }
  aws lambda invoke --function-name "$FN" --cli-binary-format raw-in-base64-out \
    --payload '{"path":"/v1/payg/agent-bait-scan","httpMethod":"POST","headers":{},"body":"{}"}' \
    "/tmp/diag_$FN.json" --query 'StatusCode' --output text >/dev/null 2>&1 || true
  head -c 320 "/tmp/diag_$FN.json" 2>/dev/null || echo "     (no response captured)"
  echo
done
echo

echo "== 6. Stage deployed recently?"
aws apigateway get-stage --rest-api-id "$API_ID" --stage-name "$STAGE" \
  --query '[deploymentId,lastUpdatedDate]' --output text
echo

echo "HOW TO READ THIS"
echo "  Step 3 names a function other than relayshield-agentic-api"
echo "    -> cause A. The resource is wired wrong. Re-run the create script;"
echo "       it is idempotent and will leave an existing method alone, so"
echo "       DELETE the bad method first:"
echo "         aws apigateway delete-method --rest-api-id $API_ID \\"
echo "           --resource-id <id from step 3> --http-method POST"
echo
echo "  Step 3 names relayshield-agentic-api, and step 5 shows that function"
echo "  returning 404 or a 250000/350000 price for the path"
echo "    -> cause B. The route is right and the CODE is stale. Push local main"
echo "       to GitHub so deploy_lambdas.yml runs. Nothing about the gateway"
echo "       needs touching."
echo
echo "  Step 5 shows relayshield-agentic-api quoting 500000 units"
echo "    -> the handler is current; anything still wrong is the gateway."
