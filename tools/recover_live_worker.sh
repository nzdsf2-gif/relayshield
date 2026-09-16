#!/bin/sh
# Download a DEPLOYED Cloudflare Worker's source, so it can be diffed against
# the repo BEFORE anything is redeployed over it.
#
#   sh tools/recover_live_worker.sh relayshield-ti-demo cloudflare_worker_ti_demo.js
#
# WHY THIS EXISTS. The DRIFT RULE in CLAUDE.md has carried the same open item
# for weeks: "The TI demo Cloudflare Worker -- still outstanding.
# recover_live_handler.yml does this for Lambdas. Nothing does it for Workers
# yet." So every Worker in this repo has the exact combination that has now cost
# this repo three recoveries: source in the repo, live traffic, and no way to
# see what is actually deployed.
#
# relayshield-ti-demo is the worst of them. No workflow deploys it -- grep
# .github/workflows and nothing matches -- so every version of it that ever went
# live was pushed by hand from somebody's machine, and a hand-deployed Worker is
# precisely where an uncommitted edit survives. `wrangler deploy` would replace
# it with the repo copy and report success.
#
# wrangler has no download command. The Workers API does, and it is one GET.
#
# READ-ONLY. It writes a file into the scratch directory and never near the
# repo copy, so the diff is something you look at rather than something that has
# already overwritten your working tree.
set -e

SCRIPT_NAME=$1
REPO_FILE=$2
[ -n "$SCRIPT_NAME" ] || { echo "usage: $0 <worker-script-name> [repo-file-to-diff]"; exit 2; }

# The token is READ, never taken as an argument and never assigned inline: an
# argument is in the process table and in shell history, and this one can deploy
# Workers. `read -rs` is the zsh form and works in sh here too; -s suppresses
# the echo. Needs "Workers Scripts: Read" at minimum.
if [ -z "$CF_API_TOKEN" ]; then
  printf 'Cloudflare API token (input hidden): '
  stty -echo 2>/dev/null || true
  read CF_API_TOKEN
  stty echo 2>/dev/null || true
  printf '\n'
fi
[ -n "$CF_API_TOKEN" ] || { echo "no token, nothing to do"; exit 2; }

# THE ACCOUNT ID IS DISCOVERED, NOT ASKED FOR, AND THE FIRST VERSION ASKED.
# It prompted "Cloudflare account id:" and the answer was an EMAIL ADDRESS --
# which is a perfectly reasonable thing to type at that prompt, and produced a
# 404 whose reading guide said "no deployed script by that name", sending the
# reader to check the Worker. The Worker was never the problem. A Cloudflare
# account id is a 32-character hex string buried in the dashboard sidebar, and
# a prompt that does not say so is rule 11's placeholder wearing a question
# mark: it looks like an instruction to whoever wrote it and is unanswerable to
# whoever reads it.
#
# The token can list the accounts it can see, so the question does not need
# asking at all. One extra GET removes a whole class of wrong answer.
if [ -z "$CF_ACCOUNT_ID" ]; then
  ACCTS="${TMPDIR:-/tmp}/cf-accounts.json"
  ACODE=$(curl -sS -o "$ACCTS" -w '%{http_code}' \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    "https://api.cloudflare.com/client/v4/accounts?per_page=50" 2>/dev/null) || true
  if [ "$ACODE" = "200" ]; then
    # PARSED, NOT GREPPED. The first version matched '"id":"..."' with no
    # space after the colon and silently extracted nothing from JSON that had
    # one -- an empty result that reads identically to "the token sees no
    # accounts". Grepping JSON is the same class as grepping the source of a
    # template literal: it works until the shape shifts by one character.
    CF_ACCOUNT_ID=$(python3 - "$ACCTS" <<'PYEOF'
import json, sys
try:
    rows = json.load(open(sys.argv[1])).get("result") or []
except Exception:
    rows = []
for r in rows:
    if isinstance(r, dict) and isinstance(r.get("id"), str) and len(r["id"]) == 32:
        print(r["id"]); break
PYEOF
)
    NAMES=$(python3 - "$ACCTS" <<'PYEOF'
import json, sys
try:
    rows = json.load(open(sys.argv[1])).get("result") or []
except Exception:
    rows = []
print(", ".join(str(r.get("name", "?")) for r in rows if isinstance(r, dict)))
PYEOF
)
    if [ -n "$CF_ACCOUNT_ID" ]; then
      echo "Account discovered from the token: $CF_ACCOUNT_ID"
      echo "  (accounts this token can see: $NAMES)"
      # MORE THAN ONE ACCOUNT IS A DECISION, NOT A DEFAULT. Taking the first
      # silently is how a read lands in the wrong account -- the same shape as
      # AWS_PROFILE defaulting to the pre-audit account.
      COUNT=$(python3 -c "import json,sys;print(len(json.load(open(sys.argv[1])).get('result') or []))" "$ACCTS" 2>/dev/null || echo 1)
      if [ "$COUNT" != "1" ]; then
        echo "  NOTE: $COUNT accounts are visible and the FIRST was taken. If the"
        echo "  Worker is in another one, re-run with CF_ACCOUNT_ID set."
      fi
    fi
  else
    echo "Could not list accounts (HTTP $ACODE). Body:"
    cat "$ACCTS" 2>/dev/null; echo
  fi
fi

if [ -z "$CF_ACCOUNT_ID" ]; then
  echo "No account id, and the token could not list one."
  echo "Find it in the Cloudflare dashboard: open any zone, and the right-hand"
  echo "sidebar shows 'Account ID' as a 32-character hex string. It is NOT an"
  echo "email address and NOT the account name."
  exit 2
fi

# Validated rather than trusted, because the failure it prevents reads as a
# missing Worker. `expr` for portability: sh has no [[ =~ ]].
if ! expr "$CF_ACCOUNT_ID" : '[0-9a-f]\{32\}$' >/dev/null; then
  echo "That is not a Cloudflare account id: $CF_ACCOUNT_ID"
  echo "It must be exactly 32 hexadecimal characters. An email address or an"
  echo "account name here returns a 404 that reads like a missing Worker."
  exit 2
fi

OUT="${TMPDIR:-/tmp}/live-worker-$SCRIPT_NAME.js"
API="https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME"

echo "GET $API"
# `|| true` because `set -e` would otherwise ABORT HERE ON A FAILED CONNECTION,
# silently and with exit 0 further down the pipe -- caught by running it against
# a blocked host rather than by reading it. A script that cannot reach the API
# must SAY SO; exiting quietly is the worst of the three outcomes, because it
# reads as "nothing to recover".
CODE=$(curl -sS -o "$OUT" -w '%{http_code}' \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Accept: application/javascript" "$API" 2>"${TMPDIR:-/tmp}/cf-curl.err") || true

if [ -z "$CODE" ] || [ "$CODE" = "000" ]; then
  echo "NO ANSWER from the Cloudflare API. This says NOTHING about the Worker:"
  echo "it is a fact about this machine's network, not about what is deployed."
  cat "${TMPDIR:-/tmp}/cf-curl.err" 2>/dev/null
  exit 1
fi

# THE BODY IS PRINTED ON A FAILURE, NOT A SUMMARY OF IT. A 403 from a token
# missing Workers:Read and a 404 from a misspelled script name are different
# problems with different fixes, and the status code alone separates neither
# from "this Worker was never deployed under that name".
if [ "$CODE" != "200" ]; then
  echo "HTTP $CODE -- not recovered. Body:"
  cat "$OUT"; echo
  echo
  echo "  403  the token cannot read Workers Scripts. Mint one with that scope."
  echo "  404  no deployed script by that name in this account. Check the name"
  echo "       against the 'name' line in the matching wrangler.*.toml, and"
  echo "       check you are in the right Cloudflare account."
  exit 1
fi

echo "Recovered $(wc -c < "$OUT") bytes -> $OUT"

[ -n "$REPO_FILE" ] || exit 0
[ -f "$REPO_FILE" ] || { echo "no such repo file: $REPO_FILE"; exit 2; }

echo
echo "=============================================================="
echo "DIFF: repo ($REPO_FILE) vs LIVE"
echo "=============================================================="
if diff -u "$REPO_FILE" "$OUT" > "${TMPDIR:-/tmp}/worker-drift.diff"; then
  echo "IDENTICAL. The repo copy is what is deployed, so a redeploy is safe"
  echo "and there is nothing to recover."
else
  echo "THEY DIFFER. Full diff: ${TMPDIR:-/tmp}/worker-drift.diff"
  echo
  head -60 "${TMPDIR:-/tmp}/worker-drift.diff"
  echo
  echo "  READ IT BEFORE DEPLOYING ANYTHING. A line present on the LIVE side"
  echo "  and in no commit is hand-deployed work, and 'wrangler deploy' would"
  echo "  delete it with no error anywhere. Recover it into git FIRST, exactly"
  echo "  as the four Lambda handlers were on 2026-08-26."
fi
