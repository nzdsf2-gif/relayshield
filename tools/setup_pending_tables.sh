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
# Or, with no repo checkout at all — it is fully self-contained:
#   curl -sSL -o /tmp/rs_setup.sh https://raw.githubusercontent.com/nzdsf2-gif/relayshield/claude/daily-todo-summary-7zpsvv/tools/setup_pending_tables.sh
#   AWS_PROFILE=relayshield bash /tmp/rs_setup.sh
#
# Dry run (prints what it would do, changes nothing):
#   AWS_PROFILE=relayshield DRY_RUN=1 bash tools/setup_pending_tables.sh

set -uo pipefail
REGION="${AWS_REGION:-us-east-1}"
DRY="${DRY_RUN:-}"
ACCT_EXPECTED="239677749008"

# IAM policies are INLINE, not file:// paths into the repo. This script has to
# work when downloaded on its own with curl, and from any working directory —
# a wrong-cwd failure is exactly what broke the drift diff on 2026-08-22
# ("relayshield_api.py: No such file or directory", run from ~).
policy_doc() {
  local sid="$1" actions="$2" table="$3"
  printf '{"Version":"2012-10-17","Statement":[{"Sid":"%s","Effect":"Allow","Action":[%s],"Resource":"arn:aws:dynamodb:%s:%s:table/%s"}]}' \
    "$sid" "$actions" "$REGION" "$ACCT_EXPECTED" "$table"
}

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
if [ "$ACCOUNT" != "$ACCT_EXPECTED" ]; then
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

grant() {   # role, policy-name, sid, actions, table
  [ -n "$1" ] && [ "$1" != "None" ] || { echo "  skip $2 — role unknown"; return 0; }
  if [ -n "$DRY" ]; then echo "  [dry-run] would attach $2 to $1"; return 0; fi
  aws iam put-role-policy --role-name "$1" --policy-name "$2" \
    --policy-document "$(policy_doc "$3" "$4" "$5")" \
    && echo "  attached $2 to $1" || echo "  FAILED to attach $2"
}

grant "$INTEL_ROLE" relayshield-ransomware-victims-write \
      IntelMonitorWriteVictims '"dynamodb:PutItem"' relayshield_ransomware_victims
grant "$INTEL_ROLE" relayshield-operator-identities-write \
      IntelMonitorWriteOperators '"dynamodb:UpdateItem"' relayshield_operator_identities
grant "$API_ROLE" relayshield-ransomware-victims-read \
      ApiReadVictims '"dynamodb:Scan","dynamodb:GetItem"' relayshield_ransomware_victims
grant "$API_ROLE" relayshield-scan-submissions-write \
      ApiWriteScanSubmissions '"dynamodb:UpdateItem","dynamodb:Scan"' relayshield_scan_submissions

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
