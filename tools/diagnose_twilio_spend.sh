#!/bin/sh
# READ-ONLY. Which of our code paths made the Twilio Lookup calls in a window?
#
#   AWS_PROFILE=relayshield sh tools/diagnose_twilio_spend.sh
#   WIN_START=2026-10-03 WIN_END=2026-10-10 AWS_PROFILE=relayshield sh tools/diagnose_twilio_spend.sh
#
# THE FIRST VERSION HUNG, AND IT WAS A DEFECT THIS REPO HAD ALREADY RECORDED.
# It counted API log lines with `aws logs filter-log-events`, which walks every
# log stream in the group and returns a next-token even for a page with no match.
# On relayshield-api for a week that is tens of thousands of invocations, so it
# printed its header and went quiet. This version uses CloudWatch Logs INSIGHTS:
# one query, a short poll, and a dot per poll on stderr so a slow query is
# distinguishable from a hung one. See "THE FUNNEL WAS HUNG, NOT BROKEN".
#
# FOUR code paths can make a Twilio Lookup, and the 2026-10-10 rate limit covers
# only B:
#   A  the SIM swap monitor, one lookup per enrolled number per run
#   B  /v1/metered/phone-reputation and /v1/metered/sim-swap on the API
#   C  the Telegram bot's /sim command, one lookup per press
#   D  the WhatsApp webhook's own lookup
# Counts only. No phone numbers, keys or chat ids are read or printed.
#
# A LOG COUNT IS A FLOOR, NOT A BILL. A path that does not log each lookup shows as
# zero and is not thereby cleared. THE BILL IS TWILIO'S: compare the totals below
# with Twilio Console > Monitor > Usage > Lookups for the same dates. If Twilio's
# count is far larger than everything counted here, the spender is C or D, or the
# calls did not come from us at all.

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
S_S=$(python3 -c "import datetime as d,sys;print(int(d.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=d.timezone.utc).timestamp()))" "$WIN_START")
E_S=$(python3 -c "import datetime as d,sys;print(int(d.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=d.timezone.utc).timestamp()))" "$WIN_END")
echo "window: $WIN_START to $WIN_END (UTC)"

# insights GROUP "QUERY"  -> echoes the results as JSON on success, or nothing.
insights() {
  QID=$(aws logs start-query --log-group-name "$1" --start-time "$S_S" --end-time "$E_S" \
        --query-string "$2" --query queryId --output text 2>/dev/null) || return 1
  [ -n "$QID" ] && [ "$QID" != "None" ] || return 1
  i=0
  while [ $i -lt 90 ]; do
    ST=$(aws logs get-query-results --query-id "$QID" --query status --output text 2>/dev/null)
    case "$ST" in
      Complete) aws logs get-query-results --query-id "$QID" --query results --output json 2>/dev/null; return 0;;
      Failed|Cancelled|Timeout) return 1;;
    esac
    printf '.' >&2; sleep 2; i=$((i+1))
  done
  return 1
}
# one_number GROUP "QUERY ending in: stats count(*) as n"
one_number() {
  R=$(insights "$1" "$2") || { echo "(not readable: query failed, or the log group is missing or denied)"; return; }
  printf '%s' "$R" | python3 -c "
import json,sys
rows=json.load(sys.stdin)
v=0
for r in rows:
    for f in r:
        if f['field']=='n': v=f['value']
print(v)"
}

hdr "A. SIM swap monitor: schedule, then runs and lookups per day"
ARN=$(aws lambda get-function-configuration --function-name relayshield-sim-swap-monitor --query FunctionArn --output text 2>/dev/null)
for R in $(aws events list-rule-names-by-target --target-arn "$ARN" --query 'RuleNames[]' --output text 2>/dev/null); do
  printf '   schedule rule: '
  aws events describe-rule --name "$R" --query '[Name,ScheduleExpression,State]' --output text 2>/dev/null
done
echo "   (its docstring says rate(4 hours): about 6 runs a day. More than that is a finding.)"
R=$(insights /aws/lambda/relayshield-sim-swap-monitor \
  'filter @message like /user\(s\) with SIM swap monitoring enabled/ | parse @message "Found * user(s)" as n | stats count(*) as runs, sum(n) as lookups by bin(1d)') \
  && printf '%s' "$R" | python3 -c "
import json,sys
rows=json.load(sys.stdin)
tot_r=tot_l=0
print('   day         runs  lookups')
for r in sorted(rows, key=lambda r: [f['value'] for f in r if f['field'].startswith('bin')][0]):
    d={f['field']:f['value'] for f in r}
    day=[v for k,v in d.items() if k.startswith('bin')][0][:10]
    runs=int(d.get('runs',0)); lk=int(float(d.get('lookups') or 0))
    tot_r+=runs; tot_l+=lk
    print(f'   {day}  {runs:>5}  {lk:>7}')
print(f'   TOTAL       {tot_r:>5}  {tot_l:>7}   <- monitor lookups in the window')
" || echo "   (not readable)"

hdr "A. Enrolled numbers now, and consented inside the window"
printf '   monitoring enabled now : '
aws dynamodb scan --table-name relayshield_users --filter-expression "sim_swap_monitoring = :t" \
  --expression-attribute-values '{":t":{"BOOL":true}}' --select COUNT --query Count --output text 2>&1 | tail -1
printf '   consent given in window: '
aws dynamodb scan --table-name relayshield_users \
  --filter-expression "sim_swap_monitoring = :t AND consent_at BETWEEN :a AND :b" \
  --expression-attribute-values "{\":t\":{\"BOOL\":true},\":a\":{\"S\":\"$WIN_START\"},\":b\":{\"S\":\"${WIN_END}T99\"}}" \
  --select COUNT --query Count --output text 2>&1 | tail -1

hdr "B. API: Twilio-backed endpoints (Logs Insights, one query each)"
printf '   keyed phone-reputation calls : '; one_number /aws/lambda/relayshield-api 'filter @message like /phone-reputation keyed/ | stats count(*) as n'; echo
printf '   free-tier calls to phone-rep : '; one_number /aws/lambda/relayshield-api 'filter @message like /free-tier call/ and @message like /phone-reputation/ | stats count(*) as n'; echo
printf '   free-tier calls to sim-swap  : '; one_number /aws/lambda/relayshield-api 'filter @message like /free-tier call/ and @message like /sim-swap/ | stats count(*) as n'; echo
printf '   rate-limited by the 50/h cap : '; one_number /aws/lambda/relayshield-api 'filter @message like /phone-rep rate limited/ | stats count(*) as n'; echo

hdr "C and D. Telegram /sim and the WhatsApp lookup"
echo "   Neither logs one line per lookup, so neither can be counted from logs."
echo "   Twilio's own usage page is the only count for them."

hdr "READING THIS"
echo "   1. Add A's TOTAL to B's keyed phone-reputation count. That is everything we can"
echo "      attribute. Compare it with Twilio Console > Monitor > Usage > Lookups for the"
echo "      same dates."
echo "   2. A large gap means C, D, or calls that did not come from our code."
echo "   3. If A's daily runs are far above 6, the monitor's schedule is the lever, not"
echo "      abuse: every extra run is an extra lookup per enrolled number."
echo
echo "== done. Paste everything above, unedited."
