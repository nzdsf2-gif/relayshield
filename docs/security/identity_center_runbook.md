# SEC 2 runbook: move human sign-in to IAM Identity Center

STATUS: steps 1 to 8 RUN AND PASSED on 2026-11-26 (phase 2 not started). The tool is `tools/wafr_identity.py` (tests: `test_wafr_identity.py`, 30 tests, checked against the real boto3 service models). Decision (founder, 2026-11-26): IAM Identity Center.

What this is for: three unmet practices under Well-Architected SEC 2. "Rely on a centralized identity provider" and "Employ user groups and attributes" are what Identity Center is. "Use temporary credentials" is only true once nothing signs in with a long-lived key, which is PHASE 2 below and is NOT done by this runbook's first half.

**This runbook does not close anything by itself.** Tick a practice only with the evidence named in the last section, in the Tool, by you.

## What changes for you

* You sign in at an AWS access portal with MFA, and the CLI uses `aws sso login`. Credentials expire (Admin: 4 hours, ReadOnly: 8).
* **Recommendation (mine, overrule it): the CLI profile `relayshield` points at the ADMIN permission set**, so every command already written in this repo, which says `AWS_PROFILE=relayshield`, keeps working. Add `relayshield-readonly` for dashboards and inventories. The cost is that your default profile can write. The benefit is that no existing doc, script or habit breaks, and the credential is temporary either way. Splitting your daily default to read-only is SEC 3 and is a separate step.
* GitHub Actions deploys are unaffected: they do not sign in as you.
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
STOP IF: the third command says `AccessDenied` on the FIRST try: IAM changes take several seconds to propagate (this happened on the first real run, 2026-11-26, and a retry passed), so wait 30 seconds and re-run only that command once. If it still fails, send me the exact text. That is a finding about how an SSO session is evaluated, not a mistake on your side, and the original MFA statement is still in place so nothing is lost.

---

## PHASE 2: "Use temporary credentials" (NOT part of the steps above)

Step 1's `legacy` rows list IAM users that still hold an active access key or a console password, with when each key was last used. Do NOT deactivate anything from that list on a hunch: a key that was used recently is a service depending on it, and deactivating it takes that service down. Come back to a session with the `legacy` output and I will hand over, one key at a time, an inactive-then-observe step (deactivate, wait, then delete) that starts with the keys last used longest ago. Anything that is a SERVICE credential rather than a human one moves to a role, which is its own build.

## What to cite when ticking in the Tool

| Practice | Tick only when | Evidence for the Note |
|---|---|---|
| Rely on a centralized identity provider | Steps 1 to 7 passed | Identity Center enabled; `wafr_identity.py --check` clean; the portal sign-in worked |
| Employ user groups and attributes | Same | Access is granted to groups `relayshield-readonly` and `relayshield-admins` through permission sets, not to a user |
| Use temporary credentials | Phase 2 finished: `legacy` empty, or every remaining key a documented service key | The `legacy` output, kept privately, and the MFA-required setting from step 3.2 |

The Tool's threshold for clearing a question is invisible. These three may or may not clear SEC 2; the count only moves when you see it move.
