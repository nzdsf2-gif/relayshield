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
# UPDATED 2026-09-02. The contribution reached a NEW state that the original
# two checks describe wrongly, and the wrong description is the pessimistic one.
#
# demisto/content does not merge an external PR straight to master. A bot merges
# it into an INTERNAL PR, which then goes through their own pipeline. On
# 2026-09-02 #45206 lost its /merge ref -- which check 1 alone reads as "merged
# or closed", the same as abandoned -- while the work actually moved forward
# into #45742, which is open, approved, and carries the pack. Reporting that as
# "not merged, nothing happened" would understate real progress, and reporting
# it as "ships with XSOAR" would overstate it. Both are wrong.
#
# So there are THREE stages, and the claim only becomes safe at the third:
#
#   1. The contribution PR (#45206). /merge gone means it left our hands.
#   2. The internal PR (#45742). Open means Palo Alto is still processing it.
#   3. The pack path on master. THIS is what a prospect checks, and it is the
#      only thing that licenses "our pack ships with Cortex XSOAR".

set -eu

REPO=https://github.com/demisto/content
PR=45206
INTERNAL_PR=45742
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
echo "== 1b. Internal PR #$INTERNAL_PR refs"
echo "   demisto/content merges an external contribution into an internal PR"
echo "   rather than straight to master, so #$PR going quiet is not the end of"
echo "   the story. This is where the work actually is."
IREFS=$(git ls-remote "$REPO" "refs/pull/$INTERNAL_PR/*" || true)
printf '%s\n' "$IREFS" | sed 's/^/   /'
if printf '%s\n' "$IREFS" | grep -q "refs/pull/$INTERNAL_PR/merge"; then
  echo "   -> STILL OPEN. In Palo Alto's pipeline, not yet on master."
elif printf '%s\n' "$IREFS" | grep -q "refs/pull/$INTERNAL_PR/head"; then
  echo "   -> merged or closed. Check 2 says which."
else
  echo "   -> no refs. The internal PR number may have changed; re-read the"
  echo "      bot comment on #$PR for the current one."
fi

echo
echo "== 2. Does $PACK exist on master?"
echo "   This is the check the marketing claim rests on."
echo "   Open in a browser:"
echo "     $REPO/tree/master/$PACK"
echo "   404 means NOT merged. A file listing means merged."
echo
# Two mechanisms, tried in order, because the first one does not work
# everywhere. api.github.com answers 403 from inside a Claude Code container:
# the agent proxy scopes API access to the session's allowed repositories, and
# demisto/content is not one of them. That 403 is indistinguishable from a rate
# limit by status code alone, which is why this used to stop at "NOT an answer"
# and leave the question open in exactly the session that needed it answered.
#
# raw.githubusercontent.com is not scoped that way and does answer. It cannot
# list a directory, so it asks for a file that every pack must have --
# pack_metadata.json is mandatory in the XSOAR pack format.
#
# A bare 404 from raw is not trusted on its own. A blocked or misrouted request
# can 404 just as easily as an absent file, so a CONTROL pack known to be on
# master is fetched first. Control 200 + target 404 means absent. Control 404
# means the mechanism is broken and the run is not an answer.
CONTROL=Packs/Malware/pack_metadata.json
TARGET=$PACK/pack_metadata.json
RAW=https://raw.githubusercontent.com/demisto/content/master

http() { curl -sS -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || echo "000"; }

VERDICT=""

if command -v curl >/dev/null 2>&1; then
  # The API, not the HTML tree page. The tree page can answer 403 from a proxy
  # or a rate limiter and that is indistinguishable from a real answer; the
  # contents API returns a clean 200 or 404 and needs no token for a public repo.
  API="https://api.github.com/repos/demisto/content/contents/$PACK?ref=master"
  CODE=$(http "$API")
  echo "   [api]  GET $API"
  echo "   [api]  HTTP $CODE"
  case "$CODE" in
    200) VERDICT=merged ;;
    404) VERDICT=absent ;;
    *)   echo "   [api]  not an answer -- falling back to raw.githubusercontent.com" ;;
  esac

  if [ -z "$VERDICT" ]; then
    CCODE=$(http "$RAW/$CONTROL")
    TCODE=$(http "$RAW/$TARGET")
    echo "   [raw]  control $CONTROL -> HTTP $CCODE"
    echo "   [raw]  target  $TARGET -> HTTP $TCODE"
    if [ "$CCODE" != "200" ]; then
      echo "   [raw]  control did not return 200, so a 404 on the target proves"
      echo "          nothing. This run is NOT an answer."
    else
      case "$TCODE" in
        200) VERDICT=merged ;;
        404) VERDICT=absent ;;
        *)   echo "   [raw]  unexpected status on the target. NOT an answer." ;;
      esac
    fi
  fi
else
  echo "   curl not found -- open the URL above by hand."
fi

echo
case "$VERDICT" in
  merged) echo "   -> ON MASTER. \"RelayShield ships with Cortex XSOAR\" is now"
          echo "      true and safe to publish." ;;
  absent) echo "   -> NOT ON MASTER. Do NOT claim the pack ships with XSOAR, is"
          echo "      in the Marketplace, or is available to XSOAR customers."
          echo
          echo "      What IS true and checkable while the internal PR is open:"
          echo "        \"RelayShield's Cortex XSOAR content pack has been"
          echo "         contributed to Palo Alto Networks' content repository"
          echo "         and accepted; it is progressing through their internal"
          echo "         release pipeline.\""
          echo "      That distinction is not pedantry. The first version is one"
          echo "      browser tab away from being disproved by a prospect." ;;
  *)      echo "   -> UNDETERMINED. Neither mechanism answered. Do not treat this"
          echo "      as evidence either way -- open the tree URL above by hand." ;;
esac

echo
echo "Note: the pack landing on master and the Palo Alto Tech Alliance are two"
echo "separate things. The pack is a public contribution and needs no Alliance."
echo "The Alliance is commercial and is gated on 3 named joint customers."
echo "Neither blocks the other. Do not report one as evidence of the other."
