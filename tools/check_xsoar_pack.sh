#!/bin/sh
# Is the RelayShield content pack actually merged into Cortex XSOAR?
#
#   sh tools/check_xsoar_pack.sh
#
# WHY THIS EXISTS. NEXT_SESSION_2026-08-20.md recorded PR #45206 as DONE weeks
# ago. On 2026-08-29 it was not: a blobless sparse clone of demisto/content at
# master (2c87a93) held 1,350 packs and ZERO files matching "relayshield"
# anywhere in the tree, while the PR's own head ref carried all 13 files of
# Packs/RelayShield/. The pack existed only on the branch.
#
# That matters commercially, not just tidily: "our pack ships with Cortex XSOAR"
# is a marketing claim a prospect can check in ten seconds, and it was false.
# Run this before the claim goes in any deck, email or landing page.
#
# Two independent checks, because either one alone can mislead:
#
#   1. The /merge ref. GitHub creates refs/pull/N/merge for an OPEN, mergeable
#      PR and deletes it when the PR merges or closes. Present means still open.
#      Cheap, no clone, but it says nothing about what landed.
#   2. The pack path on master. This is the one that decides the claim.

set -eu

REPO=https://github.com/demisto/content
PR=45206
PACK=Packs/RelayShield

echo "== 1. PR #$PR refs on $REPO"
REFS=$(git ls-remote "$REPO" "refs/pull/$PR/*" || true)
printf '%s\n' "$REFS" | sed 's/^/   /'
if printf '%s\n' "$REFS" | grep -q "refs/pull/$PR/merge"; then
  echo "   -> /merge ref PRESENT: PR #$PR is still OPEN."
elif printf '%s\n' "$REFS" | grep -q "refs/pull/$PR/head"; then
  echo "   -> /merge ref GONE, /head remains: PR #$PR is merged or closed."
  echo "      Merged and closed look identical here. Check 2 tells them apart."
else
  echo "   -> no refs at all. Wrong PR number, or the repo moved."
fi

echo
echo "== 2. Does $PACK exist on master?"
echo "   This is the check the marketing claim rests on."
echo "   Open in a browser:"
echo "     $REPO/tree/master/$PACK"
echo "   404 means NOT merged. A file listing means merged."
echo
if command -v curl >/dev/null 2>&1; then
  # The API, not the HTML tree page. The tree page can answer 403 from a proxy
  # or a rate limiter and that is indistinguishable from a real answer; the
  # contents API returns a clean 200 or 404 and needs no token for a public repo.
  API="https://api.github.com/repos/demisto/content/contents/$PACK?ref=master"
  CODE=$(curl -s -o /dev/null -w '%{http_code}' -H 'Accept: application/vnd.github+json' "$API" || echo "000")
  echo "   GET $API"
  echo "   HTTP $CODE"
  case "$CODE" in
    200) echo "   -> MERGED. The pack is on master. The claim is safe to make." ;;
    404) echo "   -> NOT MERGED. Do not claim the pack ships with XSOAR." ;;
    403) echo "   -> rate limited or blocked. This is NOT an answer -- retry later." ;;
    000) echo "   -> could not reach GitHub. This is NOT an answer." ;;
    *)   echo "   -> unexpected status. This is NOT an answer -- check by hand." ;;
  esac
else
  echo "   curl not found -- open the URL above by hand."
fi

echo
echo "Note: the pack landing on master and the Palo Alto Tech Alliance are two"
echo "separate things. The pack is a public contribution and needs no Alliance."
echo "The Alliance is commercial and is gated on 3 named joint customers."
echo "Neither blocks the other. Do not report one as evidence of the other."
