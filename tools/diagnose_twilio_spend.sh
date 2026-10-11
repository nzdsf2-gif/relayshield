#!/bin/sh
# READ-ONLY. Which of our code paths made the Twilio Lookup calls in a window?
#
#   AWS_PROFILE=relayshield sh tools/diagnose_twilio_spend.sh
#   WIN_START=2026-10-03 WIN_END=2026-10-10 AWS_PROFILE=relayshield sh tools/diagnose_twilio_spend.sh
#
# WHY. 1,407 lookups ($19.79) were billed 2026-10-03 to 10-10. There are FOUR code
# paths that can make one, and the 2026-10-10 rate limit covers only one of them:
#
#   A  the SIM swap monitor, every 4 hours, one lookup per enrolled number
#   B  /v1/metered/phone-reputation and /v1/metered/sim-swap on the API (the only
#      path the rate limit and the free-tier exclusion touch)
#   C  the Telegram bot's /sim command, one lookup per press, on the user's own number
#   D  the WhatsApp webhook's own lookup
#
# Each prints one number. Whichever sums to about 1,407 is the spender. It prints
# counts only: no phone numbers, no keys, no chat ids.
#
# A LINE COUNT IS A FLOOR, NOT A BILL. A path that does not log each lookup shows
# as zero here and is not thereby cleared; the verdict section says which paths
# cannot be counted this way.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }
hdr() { printf '\n== %s\n' "$1"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi

WIN_START="${WIN_START:-2026-10-03}"
WIN_END="${WIN_END:-2026-10-10}"
S_MS=$(python3 -c "import datetime as d,sys;print(int(d.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=d.timezone.utc).timestamp()*1000))" "$WIN_START")
E_MS=$(python3 -c "import datetime as d,sys;print(int(d.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=d.timezone.utc).timestamp()*1000))" "$WIN_END")
echo "window: $WIN_START to $WIN_END (UTC)"

# count_lines GROUP "PATTERN"  ->  number of matching log events in the window
count_lines() {
  aws logs filter-log-events --log-group-name "$1" --start-time "$S_MS" --end-time "$E_MS" \
    --filter-pattern "$2" --query 'events[].message' --output text 2>/dev/null \
    | python3 -c "import sys;t=sys.stdin.read();print(0 if not t.strip() else t.count(chr(9))+1)" 2>/dev/null || echo "?"
}

hdr "A. SIM swap monitor: runs in the window, and lookups = sum of 'Found N user(s)'"
aws logs filter-log-events --log-group-name /aws/lambda/relayshield-sim-swap-monitor \
  --start-time "$S_MS" --end-time "$E_MS" \
  --filter-pattern '"user(s) with SIM swap monitoring enabled"' \
  --query 'events[].message' --output text 2>/dev/null \
| python3 -c "
import re,sys
t=sys.stdin.read()
ns=[int(n) for n in re.findall(r'Found (\d+) user', t)]
print('   runs seen            :', len(ns))
print('   lookups (sum of N)   :', sum(ns))
print('   users per run, min/max:', (min(ns), max(ns)) if ns else 'n/a')
" 2>/dev/null || echo "   (not readable: log group missing or denied)"

hdr "A. Enrolled numbers now, and how many consented inside the window"
printf '   monitoring enabled now : '
aws dynamodb scan --table-name relayshield_users --filter-expression "sim_swap_monitoring = :t" \
  --expression-attribute-values '{":t":{"BOOL":true}}' --select COUNT --query Count --output text 2>&1 | tail -1
printf '   consent given in window: '
aws dynamodb scan --table-name relayshield_users \
  --filter-expression "sim_swap_monitoring = :t AND consent_at BETWEEN :a AND :b" \
  --expression-attribute-values "{\":t\":{\"BOOL\":true},\":a\":{\"S\":\"$WIN_START\"},\":b\":{\"S\":\"${WIN_END}T99\"}}" \
  --select COUNT --query Count --output text 2>&1 | tail -1
printf '   of those, Telegram-delivered: '
aws dynamodb scan --table-name relayshield_users \
  --filter-expression "sim_swap_monitoring = :t AND contains(delivery_channels, :c)" \
  --expression-attribute-values '{":t":{"BOOL":true},":c":{"S":"telegram"}}' --select COUNT --query Count --output text 2>&1 | tail -1

hdr "B. API: Twilio-backed endpoints"
printf '   keyed phone-reputation calls    : '; count_lines /aws/lambda/relayshield-api '"phone-reputation keyed"'
printf '   free-tier calls to phone-rep    : '; count_lines /aws/lambda/relayshield-api '"free-tier call" "phone-reputation"'
printf '   free-tier calls to sim-swap     : '; count_lines /aws/lambda/relayshield-api '"free-tier call" "sim-swap"'
printf '   rate-limited (PR #49 brake)     : '; count_lines /aws/lambda/relayshield-api '"phone-rep rate limited"'

hdr "C. Telegram bot"
printf '   webhook invocations of any kind : '; count_lines /aws/lambda/relayshield-telegram-webhook '"acquisition source"'
echo "   (/sim presses are NOT logged one per lookup: this path cannot be counted from logs)"

hdr "D. WhatsApp webhook"
echo "   (its own lookup is not logged one per call: cannot be counted from logs)"

hdr "READING THIS"
echo "   Compare A's 'lookups (sum of N)' with 1,407, then B's counts. If A is close to"
echo "   1,407 the spend is the monitor scanning enrolled numbers, which no rate limit on"
echo "   the API touches, and the question becomes WHO enrolled them. If A is small and B"
echo "   is large the API path is the spender. If neither, it is C or D."
echo
echo "== done. Paste everything above, unedited."
