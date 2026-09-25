#!/bin/sh
# Create relayshield_kit_fingerprints and confirm relayshield-api can
# read/write it. Read-mostly and idempotent -- safe to re-run.
#
#   sh tools/setup_kit_fingerprints_table.sh
#
# WHY THIS TABLE EXISTS
# ---------------------
# Scam-kit fingerprinting (2026-09-24). POST /v1/payg/scamkit-fingerprint
# turns a suspicious URL/HTML into a stable kit_<sha256> ID; this table is
# the system of record for those IDs: signals, family label, confidence
# evidence, and sighting counts. scamkit-match reads it; campaign-scan
# correlates across it.
#
# PRIVACY BY CONSTRUCTION. The key is kit_<sha256>, and the signals stored
# are hashes and hostnames only. relayshield_scamkit.strip_secrets() runs
# BEFORE hashing inside the Lambda, so a credential, token, nonce, or
# machine identifier can never reach this table -- the same reason the key
# is a hash, mirroring relayshield_bot_tokens (keyed on sha256(token)) and
# relayshield_stolen_cards (keyed on pan_hash).
#
# FAMILY STATUS. kit_family is auto-SUGGESTED only. The code can write
# "suggested" and can preserve an existing "approved", but no code path
# writes "approved" -- that status is set manually by Andrew directly on
# the item. Never flip family_status to approved from a script.
#
# THE CODE SHIPS INERT WITHOUT THIS TABLE, ON PURPOSE. _scamkit_upsert
# catches every DynamoDB error and logs a warning; nothing raises and
# nothing blocks the API response. Fingerprints simply are not persisted
# (stored:false in the response) until this runs, with no deploy needed
# once it does. No TTL: fingerprints are long-lived corpus evidence --
# first_seen/last_seen are the point, so nothing expires.
#
# Run this BEFORE the fingerprinting code is deployed (or any time after;
# the handlers degrade gracefully until then).

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
TABLE=relayshield_kit_fingerprints
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
  # HASH key only, on fingerprint_id (kit_<sha256>). Item shape written by
  # _scamkit_upsert: fingerprint_id, fingerprint_version, signals (hashes +
  # hostnames only -- secrets are stripped before hashing, never stored),
  # kit_family, family_status (suggested|approved), sightings_count,
  # first_seen, last_seen, sources[].
  aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=fingerprint_id,AttributeType=S \
    --key-schema AttributeName=fingerprint_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --query 'TableDescription.TableName' --output text
  aws dynamodb wait table-exists --table-name "$TABLE"
  echo "   created"
fi

echo
echo "== 3. Can $FUNC already read/write it?"
# THE CHEAP QUESTION FIRST, per this repo's own rule: the shared role may
# already carry a relayshield_* wildcard, in which case there is nothing to
# grant -- which matters more than usual, because that role's inline budget
# is full and its managed slots are at 11 of 10.
ROLE_ARN=$(aws lambda get-function-configuration --function-name "$FUNC" \
  --query Role --output text)
ROLE=${ROLE_ARN##*/}
echo "   role: $ROLE"
TABLE_ARN="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}"

for ACTION in dynamodb:GetItem dynamodb:PutItem dynamodb:UpdateItem dynamodb:Scan; do
  DECISION=$(aws iam simulate-principal-policy \
    --policy-source-arn "$ROLE_ARN" \
    --action-names "$ACTION" \
    --resource-arns "$TABLE_ARN" \
    --query 'EvaluationResults[0].EvalDecision' --output text 2>/dev/null || echo "simulate-failed")
  printf '   %-22s %s\n' "$ACTION" "$DECISION"
done

echo
echo "READ THE FOUR DECISIONS ABOVE:"
echo "  allowed         -- done. Nothing else to do; fingerprints start"
echo "                     persisting on the next scamkit-fingerprint call."
echo "  implicitDeny    -- a grant is needed. The shared role's inline budget"
echo "                     is FULL, so it must be a CUSTOMER-MANAGED policy,"
echo "                     and that role is already at 11 attached of 10"
echo "                     allowed. Do NOT force it: read iam_role_split.md"
echo "                     first."
echo "  simulate-failed -- says nothing about the grant, only that this"
echo "                     identity cannot run simulate-principal-policy."
echo "                     Not a finding."
echo
echo "Nothing breaks while this is outstanding: _scamkit_upsert logs"
echo "a warning and returns stored:false. It is just not yet collecting."
echo
echo "DO NOT create the Stripe meter objects from here -- those are"
echo "dashboard-created when Andrew supplies the Stripe connection."
