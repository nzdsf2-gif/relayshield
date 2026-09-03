#!/bin/sh
# Verify a handler's live function name and READ ITS DRIFT DIFF, without waiting
# for the nightly check.
#
#   sh tools/handler_drift.sh relayshield_discord_bot.py
#   sh tools/handler_drift.sh relayshield_developer_signup.py relayshield-dev-signup
#
# Argument 1 is the handler file. Argument 2 is the function name you EXPECT; it
# defaults to the filename with underscores turned into hyphens, which is the
# convention this repo mostly follows and has already been wrong once. Either
# way the name is checked against AWS rather than trusted.
#
# Run it from the repo root, on the Mac, with the relayshield profile configured.
# It is read-only: it lists functions, downloads a package and diffs. It creates
# nothing, deploys nothing and changes nothing in AWS.
#
# WHY THIS EXISTS
# ---------------
# relayshield_discord_bot.py was added to lambda_drift_check.yml on 2026-09-02
# and to deploy_lambdas.yml deliberately NOT AT ALL: no edit to that file has
# ever shipped automatically, so live may carry hand-deployed code that a
# repo-sourced deploy would delete with no error anywhere. The rule this repo
# learned at a cost of 2,583 lines is: a red diff is the alarm, READ IT before
# mapping anything in the deployer.
#
# Two things then blocked reading it. The nightly check runs at 13:00 UTC and
# had not yet run with the Discord entry in it. And the function name in that
# map is a GUESS -- nothing in the repo, in any workflow or in any doc names the
# live Discord Lambda, so "relayshield-discord-bot" was written from convention.
# A wrong name does not fail loudly there; it emits a "not readable" warning that
# reads like a permissions problem.
#
# So this script resolves the name from AWS rather than trusting the map, and
# then answers the one question that decides what happens next:
#
#   IS THE LIVE FILE EXACTLY SOME COMMIT'S VERSION OF IT?
#
#   yes -> live is merely STALE. There is nothing to recover, because every byte
#          of it is already in git. Safe to add to deploy_lambdas.yml and deploy.
#   no  -> live holds content NO COMMIT EVER HELD: hand-deployed work. RECOVER
#          IT FIRST with recover_live_handler.yml.
#
# THE FIRST VERSION OF THIS SCRIPT GOT THAT WRONG, on 2026-09-03, on its first
# real run. It classified by counting diff lines -- any '+' line meant "live
# carries something main does not" -- and a MODIFIED line produces a '+' and a
# '-' both. The one '+' in the Discord diff was
#
#     "content": rendered["text"] + UPSELL_FOOTER,
#
# which is not live-only work at all: it is main's own line as it stood one
# commit ago. The heuristic said RECOVER on a function that needed nothing of
# the sort. Counting is not the test. Matching a historical version is, and it
# is exact rather than heuristic, so this asks git directly.

set -eu

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
FILE="${1:-}"
if [ -z "$FILE" ]; then
  echo "usage: sh tools/handler_drift.sh <handler.py> [expected-function-name]" >&2
  exit 2
fi
# Default guess: relayshield_discord_bot.py -> relayshield-discord-bot.
MAPPED="${2:-$(printf '%s' "${FILE%.py}" | tr '_' '-')}"
# What to grep for when the guess is wrong: the distinguishing word in the
# handler's own name, e.g. "discord", "developer", "agentic".
NEEDLE=$(printf '%s' "${FILE%.py}" | sed 's/^relayshield[_-]//' | cut -d'_' -f1)

# AWS CLI v2 pages its output when stdout is a terminal, which stops a
# multi-command script dead at the first screenful. Same failure as git's pager.
export AWS_PAGER=""

aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

if [ ! -f "$FILE" ]; then
  echo "STOP: $FILE not found. Run this from the repo root:" >&2
  echo "  cd ~/\"Side SaaS Hustle\" && sh tools/handler_drift.sh $FILE" >&2
  exit 1
fi

echo "== 1. Which account are we actually talking to?"
GOT=$(aws sts get-caller-identity --query Account --output text)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to $GOT, not $ACCOUNT." >&2
  echo "620534471984 is the pre-audit account and holds no RelayShield resource." >&2
  exit 1
fi
echo "   $GOT -- correct."
echo

echo "== 2. What is $FILE's live function actually called?"
if aws lambda get-function-configuration --function-name "$MAPPED" \
     --query FunctionName --output text >/dev/null 2>&1; then
  FUNC="$MAPPED"
  echo "   '$MAPPED' exists. The name in lambda_drift_check.yml is CORRECT."
else
  echo "   '$MAPPED' does NOT exist. The name in lambda_drift_check.yml is WRONG."
  echo "   Searching every function for '$NEEDLE'..."
  CANDIDATES=$(aws lambda list-functions \
                 --query 'Functions[*].FunctionName' --output text \
               | tr '\t' '\n' | grep -i "$NEEDLE" || true)
  if [ -z "$CANDIDATES" ]; then
    echo
    echo "STOP: no Lambda in $ACCOUNT has '$NEEDLE' in its name." >&2
    echo "Either the bot runs under an unrelated name, or it is not deployed at" >&2
    echo "all -- which explains a missing change exactly as well as a stale" >&2
    echo "deploy does. If it is behind a Function URL, the URL's host contains" >&2
    echo "the function's URL id, and:" >&2
    echo "  AWS_PROFILE=relayshield aws lambda list-function-url-configs --no-cli-pager" >&2
    echo "maps that id back to a function name." >&2
    exit 1
  fi
  COUNT=$(echo "$CANDIDATES" | wc -l | tr -d ' ')
  echo "$CANDIDATES" | sed 's/^/     /'
  if [ "$COUNT" != "1" ]; then
    echo
    echo "STOP: $COUNT candidates. Pick the one behind the Discord interactions" >&2
    echo "endpoint, fix the entry in .github/workflows/lambda_drift_check.yml," >&2
    echo "and re-run. Do NOT drop the entry." >&2
    exit 1
  fi
  FUNC=$(echo "$CANDIDATES" | tr -d ' ')
  echo
  echo "   FIX THE MAP: change \"$MAPPED\" to \"$FUNC\" in"
  echo "   .github/workflows/lambda_drift_check.yml, then run"
  echo "   python3 test_workflows_parse.py before committing."
fi
echo "   Using: $FUNC"
echo

echo "== 3. When was it last modified, and by what?"
aws lambda get-function-configuration --function-name "$FUNC" \
  --query '{LastModified:LastModified,Runtime:Runtime,Handler:Handler,CodeSize:CodeSize}' \
  --output table
echo

echo "== 4. Download the live package and diff the handler"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
URL=$(aws lambda get-function --function-name "$FUNC" --query 'Code.Location' --output text)
curl -sS -o "$WORK/live.zip" "$URL"
if ! unzip -p "$WORK/live.zip" "$FILE" > "$WORK/live_handler.py" 2>/dev/null \
   || [ ! -s "$WORK/live_handler.py" ]; then
  echo "STOP: $FILE is not inside $FUNC's package." >&2
  echo "Package contents:" >&2
  unzip -Z1 "$WORK/live.zip" >&2
  exit 1
fi

if diff -q "$FILE" "$WORK/live_handler.py" >/dev/null; then
  echo "   NO DRIFT. Live matches main byte for byte."
  echo
  echo "   Every committed change to this handler is live. If a change still is"
  echo "   not visible, the cause is downstream of the code: a cached response,"
  echo "   a different function serving the surface, or a config value."
  exit 0
fi

diff -u "$FILE" "$WORK/live_handler.py" > "$WORK/handler.diff" || true
echo "   DRIFT. ('+' is live, '-' is main. The whole diff follows -- read it.)"
echo
cat "$WORK/handler.diff"
echo

# Is the live file EXACTLY some commit's version of this file? Every distinct
# content this file has ever had in git is the version at a commit that touched
# it, so walking those is exhaustive. An exact match means every byte of live is
# already committed and there is nothing to recover, whatever the diff's shape.
echo "== 4b. Is live exactly a committed version of $FILE?"
STALE_AT=""
for REV in $(git log --format=%H -- "$FILE"); do
  if git show "$REV:$FILE" 2>/dev/null | diff -q - "$WORK/live_handler.py" >/dev/null 2>&1; then
    STALE_AT="$REV"
    break
  fi
done
if [ -n "$STALE_AT" ]; then
  echo "   YES -- live is byte-identical to $FILE as of $(git log -1 --format='%h %ad %s' --date=short "$STALE_AT")"
  echo "   Commits to this file since then, which live is missing:"
  git --no-pager log --format='     %h %ad %s' --date=short "$STALE_AT"..HEAD -- "$FILE"
else
  echo "   NO -- live holds content that no commit of $FILE has ever held."
fi
echo

echo "== 5. Every other relayshield_*.py in the package"
# The nightly check compares one file per function. A hand-deploy that touched
# only a shared module -- relayshield_forward_analysis.py ships in both bot
# packages -- has always been invisible to it.
for MOD in $(unzip -Z1 "$WORK/live.zip" 2>/dev/null | grep '^relayshield_.*\.py$' || true); do
  [ "$MOD" = "$FILE" ] && continue
  if [ ! -f "$MOD" ]; then
    echo "   LIVE-ONLY FILE: $FUNC ships $MOD, which is not in the repo. RECOVER IT."
    continue
  fi
  unzip -p "$WORK/live.zip" "$MOD" > "$WORK/live_mod.py" 2>/dev/null || continue
  if diff -q "$MOD" "$WORK/live_mod.py" >/dev/null; then
    echo "   ok -- $MOD matches main"
  else
    echo "   DRIFT in shared module $MOD:"
    diff -u "$MOD" "$WORK/live_mod.py" || true
  fi
done
echo

echo "== 6. What to do with that"
if [ -z "$STALE_AT" ]; then
  cat <<'VERDICT'
   LIVE HOLDS CONTENT NO COMMIT EVER HELD. That is hand-deployed work, so
   RECOVER IT FIRST:

     Actions -> Recover Live Lambda Handler -> Run workflow
       function: (the name printed in step 2)
       handler:  $FILE

   That opens a branch with the live file on it. Reconcile it into main, and
   only then map the function in deploy_lambdas.yml. Deploying main over live
   before that is exactly how 2,583 lines were nearly lost on 2026-08-17.
VERDICT
else
  cat <<'VERDICT'
   LIVE IS MERELY STALE -- every byte of it is already committed, so there is
   nothing to recover. The next step is a deploy path: the function belongs in
   LAMBDA_MAP and in the paths: trigger of .github/workflows/deploy_lambdas.yml.
   Note what that does NOT do on its own -- the deployer ships a function only
   when the PUSH changed its source, so mapping it in a push that touches only
   workflow files deploys nothing. The push that maps it must also touch
   the handler file itself.
VERDICT
fi
