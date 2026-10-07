#!/bin/sh
# Create relayshield_vt_url_cache and confirm relayshield-api can use it.
# Read-mostly and idempotent -- safe to re-run.
#
#   sh tools/setup_vt_url_cache.sh
#
# WHY THIS TABLE EXISTS
# ---------------------
# The composite check falls back to a VirusTotal URL report when our own corpus and
# Safe Browsing say nothing, and caches the verdict for 24 hours so one URL is never
# looked up twice. The VT key is the FREE tier: 500 requests per UTC day, shared by
# the API, both bots and the checkemail Worker, and spent out on 2026-10-06.
#
# THE TABLE WAS NEVER CREATED AND NO SCRIPT EVER CREATED IT, so _vt_url_cache_get
# failed soft on every call and the "24h cache" was inert: every composite check
# that reached the fallback spent a VT request. The code ships inert without it on
# purpose (nothing breaks), and starts working the moment table, TTL and grant exist.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_vt_url_cache
FUNC=relayshield-api

export AWS_PAGER=""
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
  # Hash key `url_hash`, the same attribute _vt_url_cache_get and _vt_url_cache_put
  # use. (The item also carries a truncated url, which is a public link a caller
  # asked about, not an identity.)
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=url_hash,AttributeType=S \
    --key-schema AttributeName=url_hash,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. TTL -- and this is the step that is easy to skip and silently wrong"
# _vt_url_cache_put writes a `ttl` attribute. DynamoDB IGNORES that attribute
# unless TTL is ENABLED on the table, so without this step rows never expire:
# the cache would serve a URL verdict from months ago, forever, and look
# perfectly healthy while doing it. A stale "clean" is the worst thing this
# table can produce.
TTL_STATUS=$(aws dynamodb describe-time-to-live --table-name "$TABLE" \
  --query 'TimeToLiveDescription.TimeToLiveStatus' --output text 2>/dev/null || echo UNKNOWN)
echo "   current: $TTL_STATUS"
case "$TTL_STATUS" in
  ENABLED|ENABLING)
    echo "   already on -- nothing to do" ;;
  *)
    echo "   enabling on attribute 'ttl'"
    aws dynamodb update-time-to-live --table-name "$TABLE" \
      --time-to-live-specification "Enabled=true,AttributeName=ttl" \
      --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text ;;
esac

echo
echo "== 4. Can $FUNC already write to it?"
# THE CHEAP QUESTION FIRST. The shared role carries a policy per table by
# convention, but if any of them grants a relayshield_* wildcard the permission
# already exists and there is nothing to add -- which matters more than usual
# here, because that role's inline budget is FULL (26 policies, 10127/10240
# bytes) and its managed slots are at 11 of 10. A grant that is not needed is a
# grant that cannot be made.
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" \
  --query Role --output text)
ROLE=${ROLE_ARN##*/}
echo "   role: $ROLE"
TABLE_ARN="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}"

for ACTION in dynamodb:GetItem dynamodb:PutItem; do
  DECISION=$(aws iam simulate-principal-policy \
    --policy-source-arn "$ROLE_ARN" \
    --action-names "$ACTION" \
    --resource-arns "$TABLE_ARN" \
    --query 'EvaluationResults[0].EvalDecision' --output text 2>/dev/null || echo "simulate-failed")
  printf '   %-22s %s\n' "$ACTION" "$DECISION"
done

echo
echo "READ THE TWO DECISIONS ABOVE:"
echo "  allowed         -- done. Nothing else to do; the cache is live."
echo "  implicitDeny    -- run: AWS_PROFILE=relayshield ~/.rsvenv/bin/python \\"
echo "                     tools/grant_breach_cache_access.py --table $TABLE"
echo "                     (dry run first; it extends an existing managed policy)."
echo "                     Do NOT attach a new policy: the shared role is out of inline"
echo "                     budget and over its managed-policy count."
echo "  simulate-failed -- says nothing about the grant, only that this identity"
echo "                     cannot run simulate-principal-policy. Not a finding."
echo
echo "The cache degrades to a live VirusTotal call in every one of those cases, so"
echo "nothing is broken while this is outstanding. It is just not yet helping."
