#!/bin/sh
# READ-ONLY. Which Lambda functions account for the errors, and are any of them the
# customer-facing API?
#
#   AWS_PROFILE=relayshield sh tools/lambda_errors_by_function.sh
#   DAYS=14 AWS_PROFILE=relayshield sh tools/lambda_errors_by_function.sh
#
# WHY. tools/wafr_evidence.sh found 11,227 Lambda errors against 70,202 invocations
# in 7 days (16%), account-wide. That figure cannot be quoted, answered or fixed
# until it is split by function: a noisy scheduled job retrying a dead upstream is a
# different problem from the public API returning 502s.
#
# One CloudWatch call per function (about 60). Prints the top of the list, then the
# customer-facing functions separately so they cannot hide inside the total.
# Counts only. Never prints environment variables or log content.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
DAYS="${DAYS:-7}"
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was read." >&2
  exit 1
fi

START=$(python3 -c "import datetime as d,sys;print((d.datetime.now(d.timezone.utc)-d.timedelta(days=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$DAYS")
END=$(python3 -c "import datetime as d;print(d.datetime.now(d.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))")
PERIOD=$((DAYS * 86400))
echo "window: last $DAYS day(s), $START to $END"

OUT=$(mktemp)
FUNCS=$(aws lambda list-functions --query 'Functions[].FunctionName' --output text 2>/dev/null)
N=$(echo $FUNCS | wc -w | tr -d ' ')
echo "functions: $N"
i=0
for F in $FUNCS; do
  i=$((i+1)); printf '\r  reading %d/%d' "$i" "$N" >&2
  ER=$(aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Errors \
        --dimensions Name=FunctionName,Value="$F" --start-time "$START" --end-time "$END" \
        --period "$PERIOD" --statistics Sum --query 'Datapoints[0].Sum' --output text 2>/dev/null)
  IV=$(aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations \
        --dimensions Name=FunctionName,Value="$F" --start-time "$START" --end-time "$END" \
        --period "$PERIOD" --statistics Sum --query 'Datapoints[0].Sum' --output text 2>/dev/null)
  TH=$(aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Throttles \
        --dimensions Name=FunctionName,Value="$F" --start-time "$START" --end-time "$END" \
        --period "$PERIOD" --statistics Sum --query 'Datapoints[0].Sum' --output text 2>/dev/null)
  printf '%s\t%s\t%s\t%s\n' "$F" "${ER:-None}" "${IV:-None}" "${TH:-None}" >> "$OUT"
done
printf '\n' >&2

python3 - "$OUT" <<'PY'
import sys
rows = []
for line in open(sys.argv[1]):
    f, er, iv, th = line.rstrip("\n").split("\t")
    num = lambda s: float(s) if s not in ("None", "") else 0.0
    rows.append((f, num(er), num(iv), num(th)))
tot_e = sum(r[1] for r in rows); tot_i = sum(r[2] for r in rows); tot_t = sum(r[3] for r in rows)
print(f"\nTOTAL errors={tot_e:,.0f} invocations={tot_i:,.0f} throttles={tot_t:,.0f}"
      f"  error rate={(100*tot_e/tot_i if tot_i else 0):.1f}%")
print("\nTOP 12 BY ERRORS")
print(f"  {'function':<46}{'errors':>9}{'invoc':>10}{'rate':>8}{'throttles':>11}")
for f, e, i, t in sorted(rows, key=lambda r: -r[1])[:12]:
    print(f"  {f:<46}{e:>9,.0f}{i:>10,.0f}{(100*e/i if i else 0):>7.1f}%{t:>11,.0f}")
print("\nTOP 8 BY THROTTLES")
for f, e, i, t in sorted(rows, key=lambda r: -r[3])[:8]:
    if t:
        print(f"  {f:<46}{t:>9,.0f} throttled of {i:,.0f}")
print("\nCUSTOMER-FACING (public API surface)")
for f, e, i, t in rows:
    if f in ("relayshield-api", "relayshield-agentic-api", "relayshield-watchlist",
             "relayshield-developer-signup", "relayshield-mpp-settlement",
             "relayshield-telegram-webhook", "relayshield-whatsapp-webhook",
             "relayshield-stripe-webhook"):
        print(f"  {f:<46}{e:>9,.0f}{i:>10,.0f}{(100*e/i if i else 0):>7.1f}%{t:>11,.0f}")
print("\nREADING THIS: a function with a high error RATE and few invocations is a broken"
      "\nscheduled job. relayshield-api erroring is customer-facing. Throttles on any function"
      "\nwhile the account limit is 10 concurrent executions mean callers were turned away.")
PY
rm -f "$OUT"
echo
echo "== done. Paste everything above, unedited."
