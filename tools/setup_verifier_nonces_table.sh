#!/bin/sh
# Create relayshield_verifier_nonces: shared replay protection for the TAP and x401
# verifiers. Idempotent, safe to re-run.
#
#   AWS_PROFILE=relayshield sh tools/setup_verifier_nonces_table.sh
#
#   pk   S   SHA-256 of "<verifier>|<signer>|<nonce>"      hash key
#   ttl  N   epoch seconds, one hour after first sight
#
# NOTHING USES THE TABLE UNTIL THE VERIFIER LAMBDA HAS THE ENVIRONMENT VARIABLE
#   VERIFIER_NONCE_TABLE=relayshield_verifier_nonces
# so creating it, granting it and setting the variable can happen in that order without
# any request failing in between. Setting the variable BEFORE the table and the grant
# exist would make every TAP request answer `nonce_store_error`.
#
# TTL is switched on here because DynamoDB IGNORES a ttl attribute unless it is enabled
# for that name. The store tolerates late deletion (an expired row counts as absent), so
# the TTL only keeps the table small.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_verifier_nonces

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
    --attribute-definitions AttributeName=pk,AttributeType=S \
    --key-schema AttributeName=pk,KeyType=HASH \
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
  ENABLED|ENABLING) echo "   already on -- nothing to do" ;;
  *) echo "   enabling"
     aws dynamodb update-time-to-live --table-name "$TABLE" \
       --time-to-live-specification "Enabled=true,AttributeName=ttl" \
       --query 'TimeToLiveSpecification.TimeToLiveStatus' --output text ;;
esac

echo
echo "== 4. Next: let the verifier Lambda write it (dry run first), THEN set the variable."
echo "   AWS_PROFILE=relayshield python3 tools/grant_breach_cache_access.py --table $TABLE --function <lambda name>"
echo "   then add VERIFIER_NONCE_TABLE=$TABLE to that Lambda's environment, MERGING with the"
echo "   existing variables (tools/lambda_env_merge.py does this; a bare update replaces them)."
