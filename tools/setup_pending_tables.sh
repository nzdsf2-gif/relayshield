#!/usr/bin/env bash
# Create every DynamoDB table the repo's code writes to but which does not exist
# yet, grant the IAM permissions, and seed the one known operator handle.
#
# WHY THIS EXISTS
# ---------------
# Three tables have accumulated across sessions. Each one degrades the SAME
# silent way: the write fails, a warning is logged, collection continues, and
# the only outward sign is a digest line stuck at zero. Doing them one at a time
# across three sessions is how one gets forgotten.
#
# IDEMPOTENT. Re-running is safe — existing tables are reported and skipped.
#
#   AWS_PROFILE=relayshield bash tools/setup_pending_tables.sh
#
# Dry run (prints what it would do, changes nothing):
#   AWS_PROFILE=relayshield DRY_RUN=1 bash tools/setup_pending_tables.sh

set -uo pipefail
REGION="${AWS_REGION:-us-east-1}"
DRY="${DRY_RUN:-}"

run() {
  if [ -n "$DRY" ]; then echo "  [dry-run] $*"; else "$@"; fi
}

echo "=============================================================="
echo " RelayShield pending-table setup"
echo "=============================================================="

ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT" ] || [ "$ACCOUNT" = "None" ]; then
  echo "ERROR: no AWS identity. Did you forget AWS_PROFILE=relayshield?"
  exit 1
fi
echo "AWS account: $ACCOUNT"
if [ "$ACCOUNT" != "239677749008" ]; then
  # This exact mistake cost a session on 2026-08-20: a command run without the
  # profile resolved to 620534471984 and returned ResourceNotFoundException,
  # which looked like a missing Lambda and was not.
  echo "WARNING: expected 239677749008 (RelayShield). Stopping rather than"
  echo "         creating tables in the wrong account. Set AWS_PROFILE=relayshield."
  exit 1
fi
echo

table_exists() {
  aws dynamodb describe-table --table-name "$1" --region "$REGION" >/dev/null 2>&1
}

create_table() {
  local name="$1" hash_key="$2" range_key="$3"
  echo "--- $name"
  if table_exists "$name"; then
    echo "  already exists — skipping"
    return 0
  fi
  run aws dynamodb create-table \
    --table-name "$name" \
    --attribute-definitions "AttributeName=$hash_key,AttributeType=S" \
                            "AttributeName=$range_key,AttributeType=S" \
    --key-schema "AttributeName=$hash_key,KeyType=HASH" \
                 "AttributeName=$range_key,KeyType=RANGE" \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION" >/dev/null || { echo "  CREATE FAILED"; return 1; }

  [ -n "$DRY" ] || aws dynamodb wait table-exists --table-name "$name" --region "$REGION"
  run aws dynamodb update-time-to-live \
    --table-name "$name" \
    --time-to-live-specification "Enabled=true,AttributeName=ttl" \
    --region "$REGION" >/dev/null
  echo "  created, TTL enabled on 'ttl'"
}

# 1. Leak-site victims — written by relayshield_intel_monitor.py, read by
#    /v1/intel/ransomware and the ransomware-risk Telegram tier.
create_table relayshield_ransomware_victims victim_name seen_ts

# 2. Operator identities — one row per (handle, platform).
create_table relayshield_operator_identities handle platform

# 3. Scan submissions — first-seen tracking.
create_table relayshield_scan_submissions value_key kind

echo
echo "--- Seeding known operator handles"
# @bjorkanesiaaaa: published as Babuk's current administrator. A LEAD, not a
# verdict — this table is never to be exported as "known scam operators".
NOW=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
TTL=$(( $(date +%s) + 90*86400 ))
if [ -n "$DRY" ]; then
  echo "  [dry-run] would add @bjorkanesiaaaa (telegram)"
else
  aws dynamodb update-item \
    --table-name relayshield_operator_identities \
    --key '{"handle":{"S":"bjorkanesiaaaa"},"platform":{"S":"telegram"}}' \
    --update-expression "SET first_seen = if_not_exists(first_seen, :now), last_seen = :now, #ttl = :ttl, note = :note ADD sightings :one, channels :ch, categories :cat" \
    --expression-attribute-names '{"#ttl":"ttl"}' \
    --expression-attribute-values "{\":now\":{\"S\":\"$NOW\"},\":one\":{\"N\":\"1\"},\":ch\":{\"SS\":[\"manual:published-reporting\"]},\":cat\":{\"SS\":[\"ransomware\"]},\":ttl\":{\"N\":\"$TTL\"},\":note\":{\"S\":\"Babuk administrator per published reporting. UNVERIFIED LEAD.\"}}" \
    --region "$REGION" && echo "  added @bjorkanesiaaaa (telegram)"
fi

echo
echo "=============================================================="
echo " IAM — creating a table does NOT grant access to it"
echo "=============================================================="
INTEL_ROLE=$(aws lambda get-function-configuration --function-name relayshield-intel-monitor \
             --region "$REGION" --query Role --output text 2>/dev/null | awk -F/ '{print $NF}')
API_ROLE=$(aws lambda get-function-configuration --function-name relayshield-api \
           --region "$REGION" --query Role --output text 2>/dev/null | awk -F/ '{print $NF}')
echo "intel-monitor role: ${INTEL_ROLE:-<could not read>}"
echo "api role          : ${API_ROLE:-<could not read>}"
echo

if [ -n "$INTEL_ROLE" ] && [ "$INTEL_ROLE" != "None" ]; then
  run aws iam put-role-policy --role-name "$INTEL_ROLE" \
    --policy-name relayshield-ransomware-victims-write \
    --policy-document file://iam_ransomware_victims_policy.json && echo "  granted victims PutItem"
  run aws iam put-role-policy --role-name "$INTEL_ROLE" \
    --policy-name relayshield-operator-identities-write \
    --policy-document file://iam_operator_identities_policy.json && echo "  granted operators UpdateItem"
fi

if [ -n "$API_ROLE" ] && [ "$API_ROLE" != "None" ]; then
  run aws iam put-role-policy --role-name "$API_ROLE" \
    --policy-name relayshield-ransomware-victims-read \
    --policy-document file://iam_api_read_victims_policy.json && echo "  granted victims Scan/GetItem"
  run aws iam put-role-policy --role-name "$API_ROLE" \
    --policy-name relayshield-scan-submissions-write \
    --policy-document file://iam_scan_submissions_policy.json && echo "  granted submissions UpdateItem"
fi

echo
echo "=============================================================="
echo " Verify"
echo "=============================================================="
for t in relayshield_ransomware_victims relayshield_operator_identities relayshield_scan_submissions; do
  status=$(aws dynamodb describe-table --table-name "$t" --region "$REGION" \
           --query 'Table.TableStatus' --output text 2>/dev/null || echo MISSING)
  count=$(aws dynamodb scan --table-name "$t" --region "$REGION" --select COUNT \
          --query Count --output text 2>/dev/null || echo "-")
  printf "  %-38s %-10s items=%s\n" "$t" "$status" "$count"
done
echo
echo "Next: the victim table stays empty until the intel monitor runs again."
echo "The digest line 'Ransomware victims named: N (M stored)' is the read on it."
echo "N large with M zero is a permissions failure, not a quiet week."
