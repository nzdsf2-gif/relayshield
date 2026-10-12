#!/bin/sh
# READ-ONLY. WHY is a Lambda function erroring? Splits its errors by day and by kind
# and shows a few recent error lines.
#
#   AWS_PROFILE=relayshield sh tools/diagnose_lambda_errors.sh relayshield-api
#   DAYS=3 AWS_PROFILE=relayshield sh tools/diagnose_lambda_errors.sh relayshield-gas-monitor
#
# WHY. tools/lambda_errors_by_function.sh found relayshield-api at 9,171 errors in
# 46,551 invocations (19.7%) and relayshield-gas-monitor failing 2,021 of 2,021. The
# first is customer-facing; the second is a scheduled job whose count is about three
# times its schedule, which is what a job that fails every time looks like once the
# two automatic asynchronous retries are counted.
#
# Uses CloudWatch Logs INSIGHTS (one query each, a dot per poll on stderr), never
# filter-log-events, which scans every stream and hung two earlier tools in this repo.
#
# WHAT IT PRINTS IS LOG CONTENT. Log lines in this repo hash identifiers before
# writing them, but SKIM the "recent error lines" section for anything that looks
# like a key or a token before pasting it anywhere. Lines are cut to 300 characters.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
FN="$1"
DAYS="${DAYS:-7}"
WIDTH="${WIDTH:-300}"
[ -n "$FN" ] || { echo "usage: $0 <function-name>   (for example relayshield-api)" >&2; exit 2; }
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi
GROUP="/aws/lambda/$FN"
E_S=$(python3 -c "import time;print(int(time.time()))")
S_S=$((E_S - DAYS * 86400))
echo "function: $FN   log group: $GROUP   window: last $DAYS day(s)"

insights() {
  QID=$(aws logs start-query --log-group-name "$GROUP" --start-time "$S_S" --end-time "$E_S" \
        --query-string "$1" --query queryId --output text 2>/dev/null) || return 1
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
show() {  # show TITLE "QUERY" PYTHON-FORMATTER-BODY
  printf '\n== %s\n' "$1"
  R=$(insights "$2") || { echo "   (not readable: the query failed, or the log group is missing or denied)"; return; }
  printf '%s' "$R" | python3 -c "
import json,sys
rows=json.load(sys.stdin)
def val(r,k):
    for f in r:
        if f['field']==k: return f['value']
    return ''
$3
" || echo "   (could not format)"
  echo
}

show "error-ish lines per day" \
  'filter @message like /Task timed out|ERROR|Traceback|Runtime\.|Unhandled error|Status: error|Status: timeout/ | stats count(*) as n by bin(1d)' \
  "
if not rows: print('   none found')
for r in sorted(rows, key=lambda r: [f['value'] for f in r if f['field'].startswith('bin')][0]):
    d=[f['value'] for f in r if f['field'].startswith('bin')][0][:10]
    print(f\"   {d}  {val(r,'n'):>7}\")
"

show "error kinds (top 12)" \
  'parse @message /(?<kind>Task timed out after [0-9.]+ seconds|Unhandled error in [^:]+|Runtime\.[A-Za-z]+|[A-Za-z]+Error|[A-Za-z]+Exception|Status: (?:error|timeout))/ | filter ispresent(kind) | stats count(*) as n by kind | sort n desc | limit 12' \
  "
if not rows: print('   none recognised: see the recent lines below')
for r in rows: print(f\"   {val(r,'n'):>7}  {val(r,'kind')}\")
"

show "recent error lines (5, cut to $WIDTH characters; WIDTH=2000 shows more)" \
  'filter @message like /ERROR|Traceback|Unhandled error|Task timed out/ | fields @timestamp, @message | sort @timestamp desc | limit 5' \
  "
if not rows: print('   none')
for r in rows: print('   ' + val(r,'@timestamp')[:19] + '  ' + ' '.join(val(r,'@message').split())[:int('$WIDTH')])
"

show "INIT FAILURES (the function could not start): which module, and exactly when" \
  'filter @message like /Runtime\./ | parse @message /(?<kind>Runtime\.[A-Za-z]+)/ | parse @message /No module named .(?<missing>[A-Za-z0-9_.]+)/ | parse @message /Syntax error in module .(?<synmod>[A-Za-z0-9_.]+)/ | stats count(*) as n, min(@timestamp) as first, max(@timestamp) as last by kind, missing, synmod | sort n desc | limit 10' \
  "
if not rows: print('   none: no Runtime.* init failure in the window')
for r in rows:
    print(f\"   {val(r,'n'):>7}  {val(r,'kind')}  missing={val(r,'missing') or '-'}  syntax-in={val(r,'synmod') or '-'}\")
    print(f\"            first {val(r,'first')[:19]}   last {val(r,'last')[:19]}\")
"

show "init failures per hour, newest 24 hours with any" \
  'filter @message like /Runtime\.(ImportModuleError|UserCodeSyntaxError)/ | stats count(*) as n by bin(1h)' \
  "
rows=sorted(rows, key=lambda r: [f['value'] for f in r if f['field'].startswith('bin')][0])[-24:]
if not rows: print('   none')
for r in rows:
    h=[f['value'] for f in r if f['field'].startswith('bin')][0][:16]
    print(f\"   {h}  {val(r,'n'):>7}\")
"

printf '\n== how often is it invoked, and is the invoke count about 3x its schedule?\n'
show "invocation lines per day (START lines)" \
  'filter @message like /^START RequestId/ | stats count(*) as n by bin(1d)' \
  "
for r in sorted(rows, key=lambda r: [f['value'] for f in r if f['field'].startswith('bin')][0]):
    d=[f['value'] for f in r if f['field'].startswith('bin')][0][:10]
    print(f\"   {d}  {val(r,'n'):>7}\")
"
echo "READING THIS: a scheduled function that fails every run is invoked three times per"
echo "schedule tick (one attempt plus two automatic retries). A kind such as 'Task timed out'"
echo "on the API means callers waited and got a 502; 'Runtime.' means the code could not start."
echo
echo "== done. Paste everything above, unedited, after skimming the recent lines."
