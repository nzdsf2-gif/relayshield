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

if [ -z "$CF_ACCOUNT_ID" ]; then
  printf 'Cloudflare account id: '
  read CF_ACCOUNT_ID
fi
[ -n "$CF_ACCOUNT_ID" ] || { echo "no account id, nothing to do"; exit 2; }

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
