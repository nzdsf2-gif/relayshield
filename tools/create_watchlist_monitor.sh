#!/bin/sh
# Create the Mini App watchlist MONITOR: the Lambda, its own role, and the
# schedule that makes the product's central promise true.
#
#   sh tools/create_watchlist_monitor.sh
#
# Run from the repo root, on the Mac. Idempotent: every step checks first, so a
# re-run after a partial failure is safe.
#
# WHY THIS SCRIPT EXISTS AT ALL. relayshield_watchlist.py has stored watches
# since 2026-09-09 and its docstring says the chat_id is encrypted rather than
# hashed "so an alert can be sent". Nothing ever sent one: no scheduled monitor,
# no notification code, no workflow. Every user who tapped "Tell me if this
# changes" was told something that was not true.
#
# CREATE FIRST, MAP SECOND, AND relayshield_watchlist_monitor.py IS
# DELIBERATELY NOT IN deploy_lambdas.yml YET. The deployer calls
# update-function-code on whatever LAMBDA_MAP names, so mapping a function that
# does not exist turns the first push red with a ResourceNotFoundException that
# reads exactly like a broken deploy. Run this, then map it, in that order and
# no other. Its ARN is already in iam_github_deploy_invoke.json, which is
# harmless for a function that does not exist yet and means the first CI deploy
# after mapping does not repeat run 134's denied invoke probe.

set -eu
export AWS_PAGER=""

ACCOUNT="239677749008"
REGION="us-east-1"
FN="relayshield-watchlist-monitor"
TABLE="relayshield_watchlist"
IOCS="relayshield_intel_iocs"
ROLE="relayshield-watchlist-monitor-role"
PEPPER="relayshield/watchlist-pepper"
KEY_ALIAS="alias/relayshield-data-key"
RULE="relayshield-watchlist-monitor-schedule"
# Six hours. A rug happens in minutes and no polling interval catches that, so
# the honest job here is "you find out the same day, without opening the app",
# not "we are faster than the attacker". Anything tighter multiplies the vendor
# bill for a promise we could not keep either way.
SCHEDULE="rate(6 hours)"

echo "== identity =="
ACTUAL=$(AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text --no-cli-pager)
echo "account: $ACTUAL"
[ "$ACTUAL" = "$ACCOUNT" ] || { echo "REFUSING: expected $ACCOUNT, got $ACTUAL. 620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2; exit 1; }

echo
echo "== the watchlist table must already exist =="
# Reading before writing. If this is missing, tools/create_watchlist_lambda.sh
# has not been run and creating a monitor for a table that does not exist would
# produce a function that runs every six hours and fails every time.
AWS_PROFILE=relayshield aws dynamodb describe-table --table-name "$TABLE" --no-cli-pager >/dev/null \
  || { echo "STOP: $TABLE does not exist. Run tools/create_watchlist_lambda.sh first." >&2; exit 1; }
echo "$TABLE exists"

echo
echo "== role =="
if AWS_PROFILE=relayshield aws iam get-role --role-name "$ROLE" --no-cli-pager >/dev/null 2>&1; then
  echo "$ROLE exists"
else
  AWS_PROFILE=relayshield aws iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --no-cli-pager >/dev/null
  AWS_PROFILE=relayshield aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --no-cli-pager
  echo "$ROLE created"
fi

# Its OWN role. The shared relayshield-breach-check-role-1sapnwdl carries 26
# inline policies against a 10,240-byte budget that is spent, so a new function
# must never be the 27th.
#
# Scan, not just Query, and that is the one grant here worth arguing about: the
# monitor has to walk every row and the table is keyed by a hash of the user,
# so there is no key to query BY. Nothing else in this policy is wider than it
# needs to be -- UpdateItem on one table, Query on the IOC table only, and KMS
# restricted to the one alias by condition.
#
# THE SECRET ARN SAYS telegram_bot_token WITH UNDERSCORES. It said hyphens, the
# same one-character defect as the handler's own constant, and it is the half
# that would have SURVIVED fixing the name: a corrected name read against a
# hyphenated ARN moves the failure from ResourceNotFoundException to
# AccessDeniedException, which reads as a completely different bug.
#
# No comments inside the policy document itself. It is JSON on a command line
# and a `#` in it is a parse error, not a note.
AWS_PROFILE=relayshield aws iam put-role-policy --role-name "$ROLE" \
  --policy-name relayshield-watchlist-monitor-access \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:Scan\",\"dynamodb:UpdateItem\"],
       \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"},
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:Query\"],
       \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${IOCS}\"},
      {\"Effect\":\"Allow\",\"Action\":\"kms:Decrypt\",\"Resource\":\"*\",
       \"Condition\":{\"StringEquals\":{\"kms:RequestAlias\":\"${KEY_ALIAS}\"}}},
      {\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",
       \"Resource\":[\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:relayshield/telegram_bot_token-*\"]}
    ]}" --no-cli-pager
echo "policy applied"

echo
echo "== package =="
# The same dependency walk deploy_lambdas.yml does, so the zip this script
# builds and the zip CI builds hold the same files. relayshield_api.py is the
# big one: the monitor imports handle_ton_address from it rather than carrying
# a fifth copy of the TON vendor calls.
TMP=$(mktemp -d)
resolve_deps() {
  seen="$1"; queue="$1"
  while [ -n "$queue" ]; do
    cur="${queue%% *}"; queue="${queue#"$cur"}"; queue="${queue# }"
    [ -f "$cur" ] || continue
    for dep in $(grep -hoE '^[[:space:]]*(import|from) relayshield_[a-z0-9_]+' "$cur" \
                   | awk '{print $2".py"}' | sort -u); do
      case " $seen " in
        *" $dep "*) ;;
        *) seen="$seen $dep"; queue="$queue $dep" ;;
      esac
    done
  done
  echo "$seen"
}
DEPS="$(resolve_deps relayshield_watchlist_monitor.py)"
echo "packaging:$DEPS"
for f in $DEPS; do [ -f "$f" ] && cp "$f" "$TMP/"; done
(cd "$TMP" && zip -q monitor.zip ./*.py)

echo
echo "== function =="
if AWS_PROFILE=relayshield aws lambda get-function --function-name "$FN" --no-cli-pager >/dev/null 2>&1; then
  AWS_PROFILE=relayshield aws lambda update-function-code --function-name "$FN" \
    --zip-file "fileb://$TMP/monitor.zip" --no-cli-pager >/dev/null
  AWS_PROFILE=relayshield aws lambda wait function-updated-v2 --function-name "$FN"
  echo "$FN code updated"
else
  # IAM is eventually consistent and a freshly created role is not immediately
  # assumable by Lambda. The error names the role, which is misleading: nothing
  # is wrong with the role, the clock has not caught up. Same retry as
  # tools/create_watchlist_lambda.sh, which hit this on its first real run.
  CREATED=0; i=1
  while [ "$i" -le 10 ]; do
    if AWS_PROFILE=relayshield aws lambda create-function --function-name "$FN" \
        --runtime python3.12 --handler relayshield_watchlist_monitor.lambda_handler \
        --role "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
        --timeout 600 --memory-size 512 \
        --zip-file "fileb://$TMP/monitor.zip" --no-cli-pager >/dev/null 2>"$TMP/err"; then
      CREATED=1; break
    fi
    if grep -q "cannot be assumed by Lambda" "$TMP/err"; then
      echo "  role not propagated yet, attempt $i of 10, waiting 6s"
      sleep 6; i=$((i + 1)); continue
    fi
    echo "create-function failed for a reason that is not propagation:" >&2
    cat "$TMP/err" >&2; exit 1
  done
  [ "$CREATED" = "1" ] || { echo "role still not assumable after 60s. Re-run this script." >&2; exit 1; }
  echo "$FN created"
fi
rm -rf "$TMP"

echo
echo "== wait for Active =="
# create-function RETURNS before the function can be invoked. The next command
# is an invoke, and without this wait it is refused with
# "The function is currently in the following state: Pending".
AWS_PROFILE=relayshield aws lambda wait function-active-v2 --function-name "$FN"
echo "Active"

echo
echo "== prove it imports =="
# The probe returns before any DynamoDB call, so this proves the package and
# every transitive import without starting a watchlist sweep.
AWS_PROFILE=relayshield aws lambda invoke --function-name "$FN" \
  --payload '{"source":"ci.import-probe"}' --cli-binary-format raw-in-base64-out \
  /tmp/rs-watchlist-monitor-probe.json --no-cli-pager >/dev/null
cat /tmp/rs-watchlist-monitor-probe.json; echo
grep -q '"probe": true' /tmp/rs-watchlist-monitor-probe.json \
  || { echo "STOP: the probe did not return. Read the body above -- an ImportError here means a dependency is missing from the zip, not that the code is wrong." >&2; exit 1; }

echo
echo "== schedule =="
AWS_PROFILE=relayshield aws events put-rule --name "$RULE" \
  --schedule-expression "$SCHEDULE" \
  --description "Re-check watched TON targets and alert on a verdict change" \
  --no-cli-pager >/dev/null
AWS_PROFILE=relayshield aws lambda add-permission --function-name "$FN" \
  --statement-id "events-$RULE" --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACCOUNT}:rule/${RULE}" \
  --no-cli-pager >/dev/null 2>&1 || true
AWS_PROFILE=relayshield aws events put-targets --rule "$RULE" \
  --targets "Id=1,Arn=arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FN}" \
  --no-cli-pager >/dev/null
echo "$RULE -> $SCHEDULE"

echo
echo "== DONE =="
echo
echo "The first scheduled run SEEDS and alerts nobody, by design: rows written"
echo "before this monitor existed carry no snapshot, so every signal would read"
echo "as a change and every user would be messaged about every target at once."
echo "Alerts begin on the SECOND run."
echo
echo "Next, in this order:"
echo "  1. sh tools/grant_stars_watchlist_iam.sh            (read-only report first)"
echo "  2. map relayshield_watchlist_monitor.py in deploy_lambdas.yml and"
echo "     lambda_drift_check.yml, in a commit that TOUCHES the .py"
echo "  3. AWS_PROFILE=relayshield aws logs tail /aws/lambda/$FN --since 7h"
