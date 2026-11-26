# SEC 2 runbook: move human sign-in to IAM Identity Center

STATUS: DRAFT. Nothing here has run against AWS. The tool is `tools/wafr_identity.py` (tests: `test_wafr_identity.py`, 30 tests, checked against the real boto3 service models). Decision (founder, 2026-11-26): IAM Identity Center.

What this is for: three unmet practices under Well-Architected SEC 2. "Rely on a centralized identity provider" and "Employ user groups and attributes" are what Identity Center is. "Use temporary credentials" is only true once nothing signs in with a long-lived key, which is PHASE 2 below and is NOT done by this runbook's first half.

**This runbook does not close anything by itself.** Tick a practice only with the evidence named in the last section, in the Tool, by you.

## What changes for you

* You sign in at an AWS access portal with MFA, and the CLI uses `aws sso login`. Credentials expire (Admin: 4 hours, ReadOnly: 8).
* **Recommendation (mine, overrule it): the CLI profile `relayshield` points at the ADMIN permission set**, so every command already written in this repo, which says `AWS_PROFILE=relayshield`, keeps working. Add `relayshield-readonly` for dashboards and inventories. The cost is that your default profile can write. The benefit is that no existing doc, script or habit breaks, and the credential is temporary either way. Splitting your daily default to read-only is SEC 3 and is a separate step.
* GitHub Actions deploys are unaffected: they use the OIDC role, not you.
* The responder role (`relayshield-ir-responder`) trusts only an MFA-flagged principal. An Identity Center session is not expected to carry that flag (UNVERIFIED). Step 8 adds one trust statement for the SSO admin role and proves it.

## Order matters: never remove the old way in before the new way is proven

Your existing sign-in stays untouched until step 9. If anything below fails, you still have it.

---

**ANDREW RUNS THIS (step 1: merge, then read-only look at what exists):**

```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/determined-maxwell-ysrjad
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
AWS_PROFILE=relayshield python3 tools/wafr_identity.py
```

EXPECT: one block per step. Likely `TODO organization` or `ok`, and `BLOCKED identity center instance ... not enabled`. Rows under `legacy` print to YOUR terminal only: do not paste them into a repo file or an issue.
STOP IF: `Automatic merge failed`: only `docs/claude_memory/LOG_CURRENT.md` conflicting is expected, run `python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write` and then `git add docs/claude_memory/LOG_CURRENT.md` and `git commit --no-edit`; a conflict in any `.py` means two sessions edited code, tell me. STOP IF: `Refusing to run: credentials resolve to account 620534471984`: the profile is wrong. STOP IF: `blocked ... MEMBER of another organization`: tell me, it is a decision, not a build.

**ANDREW RUNS THIS (step 2, only if step 1 printed `TODO organization`):**

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield python3 tools/wafr_identity.py --step org --apply
```

EXPECT: `CHANGED   created the organization (all features)`.
STOP IF: any error: nothing was created beyond what it printed.

**ANDREW CLICKS THIS (step 3, in the AWS console, region us-east-1):**

1. IAM Identity Center, Enable. Choose the ORGANIZATION instance, in us-east-1 (the spec's region; if you enable it elsewhere, tell me and I change the spec).
2. Settings, Authentication, Multi-factor authentication: set it to require MFA EVERY time users sign in, with an authenticator app and/or security key allowed. (Console wording may differ slightly. This setting has no API in the tool, so it is the one piece of evidence you collect by screenshot for the Note.)
3. Users, Add user: your own e-mail address; pick a user name. You set the password from the invitation e-mail.

EXPECT: the Identity Center dashboard shows an "AWS access portal URL".
STOP IF: the console offers only an "account instance": that has no multi-account permission sets; tell me.

**ANDREW RUNS THIS (step 4: build the sets, groups and assignments, and add yourself):**

```zsh
cd ~/dev/relayshield
read "SSO_USER?Identity Center user name you created: "
AWS_PROFILE=relayshield python3 tools/wafr_identity.py --apply --add-user "$SSO_USER"
```

EXPECT: `CHANGED` lines for two permission sets, two groups, two assignments and two memberships; exit without `BLOCKED`.
STOP IF: `BLOCKED membership ... no Identity Center user`: the user name does not match; fix the spelling or step 3.3.

**ANDREW RUNS THIS (step 5: confirm it is all in place; assignments are asynchronous):**

```zsh
cd ~/dev/relayshield
read "SSO_USER?Identity Center user name: "
AWS_PROFILE=relayshield python3 tools/wafr_identity.py --check --add-user "$SSO_USER" --step all
```

EXPECT: `0 to change, 0 need attention` for organization, instance, permission_sets, groups, assignments, membership. (`legacy` will still list long-lived credentials: that is phase 2. `responder` shows TODO until step 8.)
STOP IF: an assignment still shows TODO after a minute: re-run once.

**ANDREW CLICKS THIS (step 6):** open the access portal URL from step 3, sign in with the user from step 3, register MFA when asked. EXPECT: the account tile shows two roles, `RelayShieldAdmin` and `RelayShieldReadOnly`. STOP IF: no roles: step 5 was not clean.

**ANDREW RUNS THIS (step 7: create the two CLI profiles, interactive, under temporary names):**

```zsh
aws configure sso --profile relayshield-sso-admin
aws configure sso --profile relayshield-sso-readonly
```

Answer the prompts: start URL from step 3, region us-east-1, then pick the account and the role (Admin for the first, ReadOnly for the second). Then:

```zsh
aws sso login --profile relayshield-sso-admin
AWS_PROFILE=relayshield-sso-admin aws sts get-caller-identity --no-cli-pager
```

EXPECT: `"Account": "239677749008"` and an `Arn` containing `AWSReservedSSO_RelayShieldAdmin_`.
STOP IF: account is anything else.

**ANDREW RUNS THIS (step 7b: swap the names so every `AWS_PROFILE=relayshield` command in the repo now uses SSO, and keep the old one as a fallback):**

```zsh
cp ~/.aws/config ~/.aws/config.pre-sso
cp ~/.aws/credentials ~/.aws/credentials.pre-sso
open -e ~/.aws/config
open -e ~/.aws/credentials
```

In `~/.aws/config`: change the heading `[profile relayshield]` to `[profile relayshield-legacy]`, then `[profile relayshield-sso-admin]` to `[profile relayshield]`, then `[profile relayshield-sso-readonly]` to `[profile relayshield-readonly]`. In `~/.aws/credentials`: change the heading `[relayshield]` to `[relayshield-legacy]`. Save both. Then:

```zsh
AWS_PROFILE=relayshield aws sts get-caller-identity --no-cli-pager
```

EXPECT: account `239677749008`, Arn containing `AWSReservedSSO_RelayShieldAdmin_`.
STOP IF: `The SSO session ... has expired`: run `aws sso login --profile relayshield` and repeat. STOP IF anything else: restore with `cp ~/.aws/config.pre-sso ~/.aws/config` and `cp ~/.aws/credentials.pre-sso ~/.aws/credentials`, and tell me. UNVERIFIED: your config file's exact headings, which I cannot see.

**ANDREW RUNS THIS (step 8: let the SSO admin role assume the responder role, then prove it):**

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield python3 tools/wafr_identity.py --step responder
AWS_PROFILE=relayshield python3 tools/wafr_identity.py --step responder --apply
AWS_PROFILE=relayshield aws sts assume-role --role-arn arn:aws:iam::239677749008:role/relayshield-ir-responder --role-session-name sso-proof --query Credentials.Expiration --output text --no-cli-pager
```

EXPECT: first command `TODO relayshield-ir-responder  add one trust statement ...`; second `CHANGED added the SSO admin statement ... (existing statement kept)`; third a single timestamp about an hour ahead.
STOP IF: the third command says `AccessDenied`: send me the exact text. That is a finding about how an SSO session is evaluated, not a mistake on your side, and the original MFA statement is still in place so nothing is lost.

---

## PHASE 2: "Use temporary credentials"

STATUS: DRAFT, built and tested (`tools/wafr_keys.py`, `test_wafr_keys.py`, 48 tests, checked against the real IAM, CloudTrail and STS models) and NOT run against AWS. Start only after steps 1 to 8 above passed.

**What it does and does not do.** It retires long-lived IAM credentials ONE AT A TIME, reversibly first. It does not move a service onto a role: a credential that a service still needs stays, and is documented privately as a service key. Whether the Tool accepts documented service keys as meeting the practice is UNKNOWN; the count only moves when you see it move.

**Three rules the tool enforces, so you do not have to remember them:**
* Every write runs only from an Identity Center session. That proves the new sign-in works before the old one goes, and stops it deactivating the key that is running it. The rollback (`--reactivate`) is exempt, so it works even if SSO is what broke.
* A key used in the last 7 days is a service depending on it, and is refused.
* Delete is refused unless the key is already Inactive and CloudTrail shows it was deactivated 7 or more days ago.

Output names users and key ids. It stays in your terminal: never paste it into a repo file or an issue, and it is not wired into any workflow on purpose.

**ANDREW RUNS THIS (P2.1: the ranked report, read-only; nothing here changes anything):**

```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield python3 tools/wafr_keys.py
```

EXPECT: three blocks (access keys, console passwords, root account), keys ranked never-used first, and a `NEXT:` line naming the safest candidate. Each key shows which service and region last used it.
STOP IF: `Refusing to run: credentials resolve to account 620534471984`: the profile is wrong. STOP IF a `BLOCKED` row: tell me the row's wording, without the key id.

**FOR INFORMATION, DO NOT RUN (how to read P2.1):**

```text
NEVER-USED / IDLE   a candidate. Go to P2.2.
IN USE              used in the last 7 days, so something depends on it. Do NOT deactivate. Find what uses it
                    (the service/region shown is the clue). If it is a service, it becomes a documented service
                    key, kept in a private note and not in this repo, and is its own later build to replace.
INACTIVE            already deactivated. Goes to P2.4 once 7 days have passed.
PASSWORD            a console password on an IAM user. Goes to P2.5.
root account key    removing it is done signed in as root, in the console: Security credentials, delete. Not here.
```

**ANDREW RUNS THIS (P2.2: preview deactivating ONE key; it asks which, so there is no placeholder):**

```zsh
cd ~/dev/relayshield
read "KEYID?Access key id to deactivate (the NEXT line of P2.1): "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --deactivate "$KEYID"
```

EXPECT: `TODO      deactivate ... (never used)` or `(last used Nd ago)`, then `Dry run only`.
STOP IF: `REFUSED ... IAM Identity Center session`: `aws sso login --profile relayshield` and run it again. STOP IF `REFUSED ... was used N day(s) ago`: do not override it; see P2.1's table. If this is the key your own old profile uses, note that deactivating it ends the `relayshield-legacy` fallback: do it only once SSO has been your daily sign-in for a few days.

**ANDREW RUNS THIS (P2.3: deactivate it, which is reversible):**

```zsh
cd ~/dev/relayshield
read "KEYID?Same access key id: "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --deactivate "$KEYID" --apply
```

EXPECT: `CHANGED   ... is now Inactive`, with the rollback command printed.
STOP IF: anything broke in the next days (a bot silent, a worker failing, a deploy red): undo it with the next block, then tell me what it was, because that is a service key.

**ANDREW RUNS THIS (rollback, any time, works without SSO):**

```zsh
cd ~/dev/relayshield
read "KEYID?Access key id to turn back on: "
AWS_PROFILE=relayshield-legacy python3 tools/wafr_keys.py --reactivate "$KEYID" --apply
```

EXPECT: `CHANGED   ... is Active again`.
STOP IF: `Refusing to run ... 620534471984`: the profile name is wrong; use whichever profile points at account 239677749008. UNVERIFIED: that `relayshield-legacy` still works, which depends on a key you may already have deactivated: if it does not, use the SSO profile (`relayshield`), which the rollback accepts too.

**OBSERVE: 7 days.** Watch whatever the key could have been serving. The tool will not let you delete sooner.

**ANDREW RUNS THIS (P2.4: after 7 days with nothing broken, delete it for good):**

```zsh
cd ~/dev/relayshield
read "KEYID?Access key id to delete: "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --delete "$KEYID"
```

EXPECT: `TODO      PERMANENTLY delete ... (Inactive N days)` and `Dry run only`. If you are happy, run the next block.
STOP IF: `BLOCKED ... CloudTrail has no UpdateAccessKey record`: if you deactivated it with this tool, add `--observed-since YYYY-MM-DD` with that date (it is used only where CloudTrail is silent, and the later date always wins). I could not verify CloudTrail's field names from here; the tool compares them case-insensitively. STOP IF `REFUSED ... Come back in N`: wait.

**ANDREW RUNS THIS (P2.4b: the permanent delete, only after reading the dry run above):**

```zsh
cd ~/dev/relayshield
read "KEYID?Access key id to delete: "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --delete "$KEYID" --apply
```

EXPECT: `CHANGED   ... is deleted.`
STOP IF: any `REFUSED` or `BLOCKED`: nothing was changed.

Repeat P2.1 to P2.4b for the next candidate. One key at a time, always.

**ANDREW RUNS THIS (P2.5: remove a human IAM user's console password, only after the SSO portal has been your sign-in for a week):**

```zsh
cd ~/dev/relayshield
read "IAMUSER?IAM user name whose console password to remove: "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --remove-console "$IAMUSER"
```

EXPECT: `TODO      remove the console password of ...` and `Dry run only`. The user and its keys stay.
STOP IF: `REFUSED ... signed in N day(s) ago`: you are still signing in the old way; use the portal and wait.

**ANDREW RUNS THIS (P2.5b: remove it, after reading the dry run above):**

```zsh
cd ~/dev/relayshield
read "IAMUSER?IAM user name whose console password to remove: "
AWS_PROFILE=relayshield python3 tools/wafr_keys.py --remove-console "$IAMUSER" --apply
```

EXPECT: `CHANGED   the console password of ... is removed.`
STOP IF: any `REFUSED` or `BLOCKED`: nothing was changed.

**Done means** P2.1 shows no `PASSWORD`, no `NEVER-USED` or `IDLE`, no root key, and every remaining `IN USE` key is one you can name and have recorded privately as a service key.

## What to cite when ticking in the Tool

| Practice | Tick only when | Evidence for the Note |
|---|---|---|
| Rely on a centralized identity provider | Steps 1 to 7 passed | Identity Center enabled; `wafr_identity.py --check` clean; the portal sign-in worked |
| Employ user groups and attributes | Same | Access is granted to groups `relayshield-readonly` and `relayshield-admins` through permission sets, not to a user |
| Use temporary credentials | Phase 2 finished (P2.1 clean except documented service keys) | The P2.1 report, kept privately, and the MFA-required setting from step 3.2. Say plainly that remaining service keys are documented, not replaced |

The Tool's threshold for clearing a question is invisible. These three may or may not clear SEC 2; the count only moves when you see it move.
