# Splitting the shared Lambda role

**Status:** tooling built and dry-run against a fixture, 2026-08-30. Nothing has
been applied in AWS yet. Step 1 needs the Mac.

---

## The problem, stated properly

Every RelayShield Lambda runs as one role: `relayshield-breach-check-role-1sapnwdl`.
It is the role the AWS console auto-created for the very first function,
`relayshield-breach-check`, and it has been the answer to every "which role?"
question since.

Its convention is one inline policy per table. TODO.md line 1753 records that as
deliberate. 26 of them now fill the role's 10,240-byte inline budget, which is a
hard IAM limit and not adjustable. On 2026-08-29 adding a single `PutItem` grant
for `relayshield_intel_first_seen` failed:

```text
An error occurred (LimitExceeded) when calling the PutRolePolicy operation:
Maximum policy size of 10240 bytes exceeded for role relayshield-breach-check-role-1sapnwdl
```

`setup_first_seen.sh` fell back to a customer-managed policy, which worked. That
fallback has its own budget: a role may have **10** managed policies attached
(20 on request, once). So the fallback is not a fix, it is the next cap.

The cap is not the bug. **One role doing everything for every function is the
bug**, and it will keep producing this on every new grant.

There is a second cost that matters more than the annoyance. A shared role means
every Lambda holds every other Lambda's permissions. `relayshield-gas-monitor`
can read `relayshield_stolen_cards`. It has no reason to and no code path that
does, but the credential it runs with is allowed to.

## What the split produces

Each of the 22 mapped functions gets `<function-name>-role`. The derived policies
are small — the largest, `relayshield-intel-monitor`, is **1,864 bytes against a
10,240-byte budget**. Every one of them has room to grow by a factor of five
before anything is near a limit, which is the actual point.

## Why the policies are derived from the shared role, not written fresh

Inferring which *actions* a Lambda needs from reading its source is how you ship a
role that works for three weeks and then fails on the quarterly sweep path with
`AccessDenied`. So the split does not do that:

- **Actions** come from the shared role's existing statements. They are known to
  work today, because they are what is running today.
- **Resources** come from `tools/iam_scan_sources.py`, which reads the source.
- A statement is dropped only when the function does not call that service at
  all, or when it does and none of that service's resources are ones this
  function uses.

Statements are matched by ARN only for services whose resources appear in source
as names: DynamoDB tables, Secrets Manager ids, Lambda invoke targets, S3
buckets. For KMS reached through `alias/relayshield-data-key`, for SES,
Rekognition and the marketplace metering APIs, the source contains no ARN to
match on, so the statement is kept whenever the function uses that service.

That rule was not theoretical. The first fixture run dropped
`relayshield-intel-monitor`'s `kms:Decrypt`, which it needs on every
encrypted-field read, because a key ARN cannot be derived from an alias in the
code. The tool was wrong and was fixed before it went near AWS.

## Why it is staged in two steps

**Step one is a pure move.** Carried-over statements keep their resource patterns
unchanged, so the function's permissions after the move are identical to before.
What changes is only *which role holds them*. If something breaks, the move is
the only candidate.

**Step two is narrowing**, behind `--narrow-wildcards`, per function, after step
one is proven. It replaces wildcards with the concrete ARNs the function uses —
`secret:relayshield/*` becomes the two secrets `relayshield-gas-monitor` actually
reads.

Doing both at once means a breakage you cannot attribute.

## Run it

Step 1 needs AWS and therefore the Mac. Steps 2 and 3 need neither.

**1. Snapshot the role first, and commit what it writes.** The 26 inline policies
exist only in AWS. Nothing is in git, no workflow checks them, and nothing would
notice if one were deleted — the DRIFT RULE, applied to IAM. This is read-only.

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_snapshot_role.py
```

If `~/.rsvenv` does not exist yet:

```zsh
python3 -m venv ~/.rsvenv
~/.rsvenv/bin/pip install boto3
```

It prints how much of the inline budget is gone, and — the part to read — **every
Lambda in the account running as this role**. That list is authoritative and the
map in `deploy_lambdas.yml` is not: 46 `relayshield_*.py` sources are not in
`LAMBDA_MAP`, and some of them are deployed handlers.

```zsh
cd ~/dev/relayshield
git add iam/snapshots && git commit -m "chore(iam): snapshot the shared Lambda role before splitting it"
```

**2. Dry-run the whole fleet.** No credentials needed.

```zsh
cd ~/dev/relayshield
python3 tools/iam_split_roles.py --from-snapshot iam/snapshots/relayshield-breach-check-role-1sapnwdl.json --write-policies /tmp/rs-policies
```

Read the dropped statements. A drop is correct when the resources belong to some
other Lambda — that is the whole point. A drop is a bug if you recognise the
table as one this function uses; if so the scanner missed a reference, and the
fix goes in `tools/iam_scan_sources.py`, not in the policy.

**3. Migrate one function, starting small.** Pick a scheduled, non-customer-facing
one so a mistake surfaces on a monitor rather than on the API.

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_split_roles.py --from-snapshot iam/snapshots/relayshield-breach-check-role-1sapnwdl.json --apply --only relayshield-gas-monitor
```

`--apply` refuses to run without `--only`. It prints the rollback command when it
finishes; keep it until the function has run once on its own schedule.

**4. Watch it run once, then do the next.** `relayshield-gas-monitor`,
`relayshield-liquidation-monitor`, `relayshield-approval-monitor` first;
`relayshield-api` and `relayshield-telegram-webhook` last.

## What this does not do

**Nothing here deletes anything from the shared role.** Reclaiming the 10,240
bytes is a separate step and is only safe once the snapshot's
`functions_using_this_role` list is empty — which includes handlers that are not
in `deploy_lambdas.yml`. Emptying it early takes down whichever unmapped Lambda
was still relying on it, with no deploy and no drift check to catch it.

Until then the budget stays full, and that is fine: a new grant now goes on the
function's own role, where there are 8,000 spare bytes.

## Regenerating the scan

`iam/required_resources.json` is generated. After changing any handler:

```zsh
cd ~/dev/relayshield
python3 tools/iam_scan_sources.py --print
```

`--check` exits non-zero if it is stale.

`iam/known_non_resources.json` records literals that look like table names and
are not — Stripe meter event names like `relayshield_secret_scan_calls`, the
alert `source` value `relayshield_internal`, the bot handle `relayshield_bot`.
Every `relayshield_*` literal in all 22 packages is currently either classified
as a table or listed there, so anything landing in `unclassified` is genuinely
new and worth a look. Adding a name there grants nothing; it only suppresses a
prompt.
