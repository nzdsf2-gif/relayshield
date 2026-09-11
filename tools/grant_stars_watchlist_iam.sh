#!/bin/sh
# Does the Telegram webhook's role have what grant_slots needs? Report, then grant.
#
#   sh tools/grant_stars_watchlist_iam.sh            read-only report
#   sh tools/grant_stars_watchlist_iam.sh --apply    grant what is missing
#
# WHY THIS IS TWO STEPS AND NOT ONE. CLAUDE.md's rule C: an instruction that
# writes to a live shared surface is preceded by the one that READS it. The
# shared role here is relayshield-breach-check-role-1sapnwdl, which runs
# roughly 42 Lambdas, carries 26 inline policies against a spent 10,240-byte
# budget, and is the role a previous session could not add a single PutItem to.
# Writing to it blind is how that budget got spent.
#
# WHAT IS MISSING AND WHY. handle_stars_payment in relayshield_telegram_webhook.py
# imports grant_slots from relayshield_watchlist, which writes the entitlement
# row and reads the HMAC pepper. The webhook has never touched either, so
# without this grant a Stars purchase SUCCEEDS, the money moves, and the credit
# fails with an AccessDenied the buyer never sees. That is the worst shape a
# failure can take here, which is why it is a script rather than a note.
#
# INLINE IS REFUSED ON PURPOSE. The budget is full and a 27th inline policy is
# how you find that out the expensive way, so this uses a CUSTOMER-MANAGED
# policy (separate budget: 10 per role, 6,144 chars each) exactly as
# tools/setup_first_seen.sh had to.

set -eu
export AWS_PAGER=""

ACCOUNT="239677749008"
REGION="us-east-1"
FN="relayshield-telegram-webhook"
TABLE="relayshield_watchlist"
PEPPER="relayshield/watchlist-pepper"
POLICY="relayshield-stars-watchlist-grant"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

echo "== identity =="
ACTUAL=$(AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text --no-cli-pager)
echo "account: $ACTUAL"
[ "$ACTUAL" = "$ACCOUNT" ] || { echo "REFUSING: expected $ACCOUNT, got $ACTUAL." >&2; exit 1; }

echo
echo "== 1. which role does the webhook actually run as =="
# Resolved from AWS, never from a map. tools/discord_bot_drift.sh learned this:
# a function name or role taken from a workflow file is a guess, and the answer
# is one describe away.
ROLE_ARN=$(AWS_PROFILE=relayshield aws lambda get-function-configuration \
  --function-name "$FN" --query 'Role' --output text --no-cli-pager)
ROLE="${ROLE_ARN##*/}"
echo "$FN runs as: $ROLE"

echo
echo "== 2. what that role already has =="
echo "-- inline policies --"
AWS_PROFILE=relayshield aws iam list-role-policies --role-name "$ROLE" \
  --query 'PolicyNames' --output text --no-cli-pager | tr '\t' '\n' | sed 's/^/   /'
echo "-- attached managed policies --"
AWS_PROFILE=relayshield aws iam list-attached-role-policies --role-name "$ROLE" \
  --query 'AttachedPolicies[].PolicyName' --output text --no-cli-pager | tr '\t' '\n' | sed 's/^/   /'

echo
echo "== 3. can it do what grant_slots needs, TODAY =="
# simulate-principal-policy against the ROLE, never a call from the operator's
# own shell: the operator is relayshield-deployer and testing that identity
# would answer a question nobody asked.
for PAIR in "dynamodb:GetItem|arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}" \
            "dynamodb:PutItem|arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}" \
            "secretsmanager:GetSecretValue|arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:${PEPPER}"; do
  ACT="${PAIR%%|*}"; RES="${PAIR#*|}"
  DEC=$(AWS_PROFILE=relayshield aws iam simulate-principal-policy \
    --policy-source-arn "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
    --action-names "$ACT" --resource-arns "$RES" \
    --query 'EvaluationResults[0].EvalDecision' --output text --no-cli-pager 2>/dev/null || echo "simulate-failed")
  printf '   %-38s %s\n' "$ACT" "$DEC"
done

if [ "$APPLY" = "0" ]; then
  echo
  echo "READ-ONLY. Nothing was changed."
  echo "EXPECT: three lines above. 'allowed' on all three means Stars are already"
  echo "        wired and there is nothing to do."
  echo "STOP IF: any line says 'implicitDeny' -- that is the grant this script"
  echo "        adds. Re-run with --apply."
  echo "STOP IF: any line says 'simulate-failed' -- the operator identity cannot"
  echo "        call iam:SimulatePrincipalPolicy, which is a different problem"
  echo "        and is NOT evidence about the webhook's permissions."
  exit 0
fi

echo
echo "== 4. grant, as a CUSTOMER-MANAGED policy =="
DOC="{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Sid\":\"StarsWatchlistGrant\",\"Effect\":\"Allow\",
     \"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\"],
     \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"},
    {\"Sid\":\"StarsWatchlistPepper\",\"Effect\":\"Allow\",
     \"Action\":\"secretsmanager:GetSecretValue\",
     \"Resource\":\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:${PEPPER}-*\"}
  ]}"

ARN="arn:aws:iam::${ACCOUNT}:policy/${POLICY}"
if AWS_PROFILE=relayshield aws iam get-policy --policy-arn "$ARN" --no-cli-pager >/dev/null 2>&1; then
  echo "$POLICY exists, adding a new default version"
  AWS_PROFILE=relayshield aws iam create-policy-version --policy-arn "$ARN" \
    --policy-document "$DOC" --set-as-default --no-cli-pager >/dev/null
else
  AWS_PROFILE=relayshield aws iam create-policy --policy-name "$POLICY" \
    --description "Let the Telegram webhook credit a Stars watch-slot purchase" \
    --policy-document "$DOC" --no-cli-pager >/dev/null
  echo "$POLICY created"
fi
AWS_PROFILE=relayshield aws iam attach-role-policy --role-name "$ROLE" \
  --policy-arn "$ARN" --no-cli-pager
echo "attached to $ROLE"

echo
echo "== 5. prove it, against the role =="
# IAM is eventually consistent, so a simulate seconds after an attach can still
# say implicitDeny. That is the clock, not the grant -- the same propagation
# race create_watchlist_lambda.sh hit twice.
i=1
while [ "$i" -le 10 ]; do
  DEC=$(AWS_PROFILE=relayshield aws iam simulate-principal-policy \
    --policy-source-arn "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
    --action-names dynamodb:PutItem \
    --resource-arns "arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}" \
    --query 'EvaluationResults[0].EvalDecision' --output text --no-cli-pager)
  [ "$DEC" = "allowed" ] && { echo "dynamodb:PutItem -> allowed"; break; }
  echo "  still $DEC, attempt $i of 10, waiting 5s"
  sleep 5; i=$((i + 1))
done
[ "$DEC" = "allowed" ] || { echo "STOP: still $DEC after 50s. Read step 2 -- the role may have an explicit Deny, which no Allow can override." >&2; exit 1; }
echo
echo "DONE. A Stars purchase can now be credited."
