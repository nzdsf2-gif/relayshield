#!/bin/sh
# Turn on point-in-time recovery and deletion protection for the tables that hold
# state nobody can regenerate. Dry run by default.
#
#   AWS_PROFILE=relayshield sh tools/protect_dynamodb_tables.sh            # reads only
#   AWS_PROFILE=relayshield sh tools/protect_dynamodb_tables.sh --apply
#
# WHY. tools/wafr_evidence.sh found 57 tables, PITR OFF on 19, deletion protection
# off on 50, and no AWS Backup plan. That is the Well-Architected answer to "how do
# you back up data" being "mostly not". Most of the 19 are caches and reproducible
# collections and do not need it. The ones below do:
#
#   customer state   watchlist (paid slots), verdict_watches, discord_installs
#   evidence         intel_first_seen (the lead-time claim rests on it and it has no
#                    TTL on purpose), operator_identities, kit_fingerprints,
#                    marketplace_listings
#
# LEFT OFF ON PURPOSE, each reproducible or disposable: breach_cache, vt_url_cache,
# secret_scan_cache, tap_nonces (caches and nonces), mcp_taxonomy (loaded from the
# repo), telemetry, rsscan_installs, scan_submissions, address_first_seen,
# intel_feed_current, intel_messages, ransomware_victims. Edit PROTECT below if you
# disagree: intel_messages and ransomware_victims are the two worth a second look,
# and the dry run prints sizes so the cost of PITR (about $0.20 per GB-month) is
# visible before anything is enabled.
#
# Both settings are free to leave on, additive and reversible. PITR enabling is
# asynchronous: the table keeps serving while the first restore point is built.
# A denied call prints the AWS error and the script carries on to the next table.

PROFILE=relayshield
REGION=us-east-1
ACCOUNT=239677749008
PROTECT="relayshield_watchlist relayshield_verdict_watches relayshield_discord_installs relayshield_intel_first_seen relayshield_operator_identities relayshield_kit_fingerprints relayshield_marketplace_listings"
export AWS_PAGER=""
aws() { command aws --profile "$PROFILE" --region "$REGION" --no-cli-pager "$@"; }

APPLY=0
[ "$1" = "--apply" ] && APPLY=1

GOT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ "$GOT" != "$ACCOUNT" ]; then
  echo "STOP: profile '$PROFILE' resolves to '$GOT', not $ACCOUNT. Nothing was changed." >&2
  exit 1
fi
[ $APPLY -eq 1 ] && echo "APPLY MODE" || echo "DRY RUN (nothing will be changed)"
echo
printf '%-40s %10s %6s %6s\n' TABLE "SIZE_MB" PITR DELPROT

CHANGED=0
for T in $PROTECT; do
  INFO=$(aws dynamodb describe-table --table-name "$T" --query '[Table.TableSizeBytes,Table.DeletionProtectionEnabled]' --output text 2>&1)
  case "$INFO" in
    *Exception*|*rror*|*enied*) printf '%-40s %s\n' "$T" "(not found or not readable: $INFO)"; continue;;
  esac
  BYTES=$(echo "$INFO" | cut -f1); DEL=$(echo "$INFO" | cut -f2)
  MB=$(python3 -c "print(round(int('${BYTES:-0}')/1048576,1))")
  PITR=$(aws dynamodb describe-continuous-backups --table-name "$T" --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus' --output text 2>&1)
  printf '%-40s %10s %6s %6s\n' "$T" "$MB" "$PITR" "$DEL"
  if [ $APPLY -eq 1 ]; then
    if [ "$PITR" != "ENABLED" ]; then
      aws dynamodb update-continuous-backups --table-name "$T" \
        --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
        --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription.PointInTimeRecoveryStatus' --output text 2>&1 | sed 's/^/     PITR -> /'
      CHANGED=$((CHANGED+1))
    fi
    if [ "$DEL" != "True" ]; then
      aws dynamodb update-table --table-name "$T" --deletion-protection-enabled \
        --query 'TableDescription.DeletionProtectionEnabled' --output text 2>&1 | sed 's/^/     deletion protection -> /'
      CHANGED=$((CHANGED+1))
    fi
  fi
done
echo
if [ $APPLY -eq 1 ]; then
  echo "changes attempted: $CHANGED. Re-run without --apply to confirm every row reads ENABLED / True."
else
  echo "Re-run with --apply to enable PITR and deletion protection on the rows above."
fi
