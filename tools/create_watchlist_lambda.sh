#!/bin/sh
# Create the watchlist table, the pepper, the Lambda, its role and its routes.
#
#   sh tools/create_watchlist_lambda.sh
#
# Run from the repo root, on the Mac. Idempotent: every step checks first, so a
# re-run after a partial failure is safe.
#
# WHY A NEW FUNCTION AND NOT A BRANCH IN AN EXISTING HANDLER: the same reason
# relayshield_mpp_settlement.py is its own file. A new file has no live
# counterpart, so it cannot drift from one. And it must NOT go into
# deploy_lambdas.yml until it exists in AWS -- the deployer calls
# update-function-code on whatever LAMBDA_MAP names, so mapping a function that
# does not exist turns the first push red with a ResourceNotFoundException that
# reads exactly like a broken deploy. Create first, map second.
#
# THE PEPPER IS GENERATED HERE AND NEVER PRINTED. It is the difference between a
# hashed partition key and a reversible one, because Telegram ids are sequential
# integers that enumerate in minutes against an unpeppered digest.

set -eu
export AWS_PAGER=""

ACCOUNT="239677749008"
REGION="us-east-1"
FN="relayshield-watchlist"
TABLE="relayshield_watchlist"
ROLE="relayshield-watchlist-role"
PEPPER="relayshield/watchlist-pepper"
KEY_ALIAS="alias/relayshield-data-key"

echo "== identity =="
ACTUAL=$(AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text --no-cli-pager)
echo "account: $ACTUAL"
[ "$ACTUAL" = "$ACCOUNT" ] || { echo "REFUSING: expected $ACCOUNT, got $ACTUAL. 620534471984 is the pre-audit account and a WRITE there SUCCEEDS silently." >&2; exit 1; }

echo
echo "== table =="
if AWS_PROFILE=relayshield aws dynamodb describe-table --table-name "$TABLE" --no-cli-pager >/dev/null 2>&1; then
  echo "$TABLE exists"
else
  AWS_PROFILE=relayshield aws dynamodb create-table \
    --table-name "$TABLE" \
    --attribute-definitions AttributeName=user_key,AttributeType=S AttributeName=target_id,AttributeType=S \
    --key-schema AttributeName=user_key,KeyType=HASH AttributeName=target_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST --no-cli-pager >/dev/null
  AWS_PROFILE=relayshield aws dynamodb wait table-exists --table-name "$TABLE"
  echo "$TABLE created"
fi

echo
echo "== pepper =="
if AWS_PROFILE=relayshield aws secretsmanager describe-secret --secret-id "$PEPPER" --no-cli-pager >/dev/null 2>&1; then
  echo "$PEPPER exists, leaving it alone"
  echo "NOTE: rotating this pepper orphans every existing watch, because the"
  echo "      partition key is derived from it. That is the cost of the key not"
  echo "      being reversible, and it is the right trade."
else
  # Generated locally, never echoed, never in shell history.
  AWS_PROFILE=relayshield aws secretsmanager create-secret --name "$PEPPER" \
    --description "HMAC pepper for the Mini App watchlist partition key" \
    --secret-string "$(openssl rand -hex 32)" --no-cli-pager >/dev/null
  echo "$PEPPER created"
fi

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

# Its OWN role, per the IAM section: the shared role's inline budget is spent and
# a new function must never be the 27th policy on it.
AWS_PROFILE=relayshield aws iam put-role-policy --role-name "$ROLE" \
  --policy-name relayshield-watchlist-access \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\",\"dynamodb:Query\",\"dynamodb:DeleteItem\"],
       \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"},
      {\"Effect\":\"Allow\",\"Action\":[\"kms:Encrypt\",\"kms:Decrypt\"],\"Resource\":\"*\",
       \"Condition\":{\"StringEquals\":{\"kms:RequestAlias\":\"${KEY_ALIAS}\"}}},
      {\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",
       \"Resource\":[\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:${PEPPER}-*\",
                     \"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:relayshield/telegram_bot_token-*\"]}
    ]}" --no-cli-pager
echo "policy applied"

echo
echo "== function =="
TMP=$(mktemp -d)
cp relayshield_watchlist.py "$TMP/"
(cd "$TMP" && zip -q watchlist.zip relayshield_watchlist.py)

if AWS_PROFILE=relayshield aws lambda get-function --function-name "$FN" --no-cli-pager >/dev/null 2>&1; then
  AWS_PROFILE=relayshield aws lambda update-function-code --function-name "$FN" \
    --zip-file "fileb://$TMP/watchlist.zip" --no-cli-pager >/dev/null
  AWS_PROFILE=relayshield aws lambda wait function-updated-v2 --function-name "$FN"
  echo "$FN code updated"
else
  # RETRY, BECAUSE IAM IS EVENTUALLY CONSISTENT AND THIS FAILED ON ITS FIRST
  # REAL RUN (2026-09-09):
  #
  #   InvalidParameterValueException ... The role defined for the function
  #   cannot be assumed by Lambda.
  #
  # Nothing was wrong with the role. It was created seconds earlier and the
  # trust policy had not yet propagated to the Lambda service. That is a
  # documented AWS behaviour and the documented answer is to retry, not to
  # change anything -- which is why the message is so misleading: it names the
  # role as the problem when the problem is the clock.
  #
  # The first version of this script called create-function immediately after
  # create-role, so it was GUARANTEED to hit this on a fresh account and to
  # work on the re-run, which is the worst kind of intermittent.
  CREATED=0
  i=1
  while [ "$i" -le 10 ]; do
    if AWS_PROFILE=relayshield aws lambda create-function --function-name "$FN" \
        --runtime python3.12 --handler relayshield_watchlist.lambda_handler \
        --role "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
        --timeout 15 --memory-size 256 \
        --zip-file "fileb://$TMP/watchlist.zip" --no-cli-pager >/dev/null 2>"$TMP/err"; then
      CREATED=1
      break
    fi
    if grep -q "cannot be assumed by Lambda" "$TMP/err"; then
      echo "  role not propagated yet, attempt $i of 10, waiting 6s"
      sleep 6
      i=$((i + 1))
      continue
    fi
    echo "create-function failed for a reason that is not propagation:" >&2
    cat "$TMP/err" >&2
    exit 1
  done
  [ "$CREATED" = "1" ] || { echo "role still not assumable after 60s. Re-run this script." >&2; exit 1; }
  echo "$FN created"
fi
rm -rf "$TMP"

echo
echo "== wait for the function to become Active =="
# THE SECOND THING THIS SCRIPT GOT WRONG ON A REAL RUN (2026-09-09):
#
#   ResourceConflictException ... The operation cannot be performed at this
#   time. The function is currently in the following state: Pending
#
# create-function RETURNS before the function can be invoked. Lambda provisions
# it asynchronously, so a freshly created function sits in Pending for a few
# seconds and every invoke against it is refused. Exactly the same class as the
# IAM propagation retry above -- an operation that succeeds, followed
# immediately by one that assumes it finished -- and it failed for exactly the
# same reason: the script did the next thing at machine speed.
#
# `wait function-active-v2` is the documented answer and it is one line. It
# polls GetFunction until State leaves Pending, so it is a no-op on the
# update path and on any re-run.
AWS_PROFILE=relayshield aws lambda wait function-active-v2 --function-name "$FN"
echo "Active"

echo
echo "== prove it imports =="
AWS_PROFILE=relayshield aws lambda invoke --function-name "$FN" \
  --payload '{"source":"ci.import-probe"}' --cli-binary-format raw-in-base64-out \
  /tmp/rs-watchlist-probe.json --no-cli-pager >/dev/null
cat /tmp/rs-watchlist-probe.json; echo

echo
echo "Expect: {\"statusCode\": 200, \"body\": \"{\\\"ok\\\": true, \\\"probe\\\": true}\"}"
echo
echo "NEXT, in this order:"
echo "  1. sh tools/create_watchlist_routes.sh"
echo "     Wires the three /v1/watchlist/* routes AND their OPTIONS preflights,"
echo "     then proves one end to end. Without it the Mini App gets a 403 that"
echo "     reads like an auth failure."
echo "  2. Only THEN add relayshield_watchlist.py to deploy_lambdas.yml, and the"
echo "     commit that maps it must touch the .py or the deployer ships nothing."
