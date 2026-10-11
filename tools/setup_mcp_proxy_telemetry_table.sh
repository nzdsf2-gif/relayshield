#!/bin/sh
# Create relayshield_mcp_proxy_telemetry. Idempotent, safe to re-run.
#
#   AWS_PROFILE=relayshield sh tools/setup_mcp_proxy_telemetry_table.sh
#
# ONE TABLE, THREE ROW KINDS (pk / sk):
#   INSTALL#<id>  REPORT#<ts>   one row per accepted report (counts), TTL 180 days
#   CAND#<hash>   CAND          a CANDIDATE indicator: a claim, never a finding.
#                               status starts "unreviewed"; TTL 365 days
#   RATE#<id>     <hour>        per-install hourly report counter, TTL 2 days
#
# THE CODE SHIPS INERT WITHOUT THIS TABLE. POST /v1/telemetry/mcp-proxy answers
# 503 until it exists and the role can write it, and the proxy drops a failed
# send. Nothing else is affected.
#
# TTL is switched on here because DynamoDB IGNORES a ttl attribute unless it is
# enabled for that name: without this step reports and candidates never expire.
#
# This table is NOT the IOC corpus and nothing here writes to it. Promoting a
# candidate into the corpus is a separate, reviewed step that does not exist yet.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_mcp_proxy_telemetry

aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT." >&2
  echo "Nothing has been created." >&2
  exit 1
fi
echo "   $GOT  (correct)"

echo
echo "== 2. Table $TABLE"
if aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
  echo "   already exists -- leaving it alone"
else
  echo "   not present -- creating"
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
    --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. TTL on attribute 'ttl'"
TTL_STATUS=$(aws dynamodb describe-time-to-live --table-name "$TABLE" \
  --query 'TimeToLiveDescription.TimeToLiveStatus' --output text 2>/dev/null || echo UNKNOWN)
echo "   current: $TTL_STATUS"
case "$TTL_STATUS" in
  ENABLED|ENABLING)
    echo "   already on -- nothing to do" ;;
  *)
    echo "   enabling"
    aws dynamodb update-time-to-live --table-name "$TABLE" \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text ;;
esac

echo
echo "== 4. Next: let relayshield-api write it (dry run first)."
echo "   AWS_PROFILE=relayshield python3 tools/grant_breach_cache_access.py --table $TABLE"
