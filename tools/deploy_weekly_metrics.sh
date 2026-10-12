#!/bin/sh
# Hand-deploy relayshield_weekly_metrics.py. It has no CI deploy path (it is in
# neither deploy_lambdas.yml's LAMBDA_MAP nor the invoke policy), so a merge to
# main changes nothing in AWS until this runs.
#
#   AWS_PROFILE=relayshield sh tools/deploy_weekly_metrics.sh            # deploy only
#   AWS_PROFILE=relayshield sh tools/deploy_weekly_metrics.sh --invoke   # deploy, then send the report now
#   ... --invoke --raise-timeout     # also set the function timeout to 300s if it is lower
#
# Read tools/handler_drift.sh output FIRST: it must say live is merely stale.
# The file imports nothing else in this repo (stdlib + boto3 only), so the
# package is the one file.
set -eu

FUNC=relayshield-weekly-metrics
ACCOUNT=239677749008
REGION=us-east-1
export AWS_PAGER=""

cd "$(dirname "$0")/.."
[ -f relayshield_weekly_metrics.py ] || { echo "STOP: relayshield_weekly_metrics.py not found"; exit 1; }

got=$(aws sts get-caller-identity --query Account --output text --no-cli-pager)
[ "$got" = "$ACCOUNT" ] || { echo "STOP: credentials resolve to account $got, not $ACCOUNT. Run with AWS_PROFILE=relayshield."; exit 1; }

python3 -m py_compile relayshield_weekly_metrics.py || { echo "STOP: the file does not compile"; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp relayshield_weekly_metrics.py "$work/"
( cd "$work" && zip -q weekly_metrics.zip relayshield_weekly_metrics.py )

aws lambda update-function-code --function-name "$FUNC" --zip-file "fileb://$work/weekly_metrics.zip" \
    --region "$REGION" --no-cli-pager --query '{LastModified:LastModified,CodeSize:CodeSize}' --output table
aws lambda wait function-updated --function-name "$FUNC" --region "$REGION"

echo
echo "== deployed. Timeout matters: the report now scans the first-seen table three times."
aws lambda get-function-configuration --function-name "$FUNC" --region "$REGION" --no-cli-pager \
    --query '{Timeout:Timeout,MemoryMB:MemorySize,LastModified:LastModified,Handler:Handler}' --output table
t=$(aws lambda get-function-configuration --function-name "$FUNC" --region "$REGION" --no-cli-pager --query Timeout --output text)
if [ "$t" -lt 300 ]; then
    if printf '%s' "$*" | grep -q -- '--raise-timeout'; then
        echo "Timeout is ${t}s; raising it to 300s (the only field changed; the environment block is untouched)."
        aws lambda update-function-configuration --function-name "$FUNC" --region "$REGION" --timeout 300 \
            --no-cli-pager --query '{Timeout:Timeout}' --output table
        aws lambda wait function-updated --function-name "$FUNC" --region "$REGION"
    else
        echo "WARNING: Timeout is ${t}s. A timeout means NO email is sent. Re-run with --raise-timeout before relying on the Monday run."
        if [ "${1:-}" = "--invoke" ]; then
            echo "Not invoking: it may time out before it sends. Re-run with --invoke --raise-timeout."
            exit 2
        fi
    fi
fi

if printf '%s' "$*" | grep -q -- '--invoke'; then
    echo
    echo "== invoking once; the email arrives at the report address within a minute or two."
    out="$work/out.json"
    aws lambda invoke --function-name "$FUNC" --region "$REGION" --no-cli-pager "$out" \
        --query '{StatusCode:StatusCode,FunctionError:FunctionError}' --output table
    head -c 400 "$out"; echo
fi
