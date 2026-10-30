# Operating model: ownership, change requests, escalation, communications

**STATUS: DRAFT, written 2026-10-29 by Claude from the repo. NOT ADOPTED.** Every statement marked CONFIRM is something only
the owner can state truthfully. The Well-Architected Tool's operational-excellence practices ask whether these mechanisms
exist. For a one-person company the honest answer is a short document and not a pretended team, so this document says that.
It becomes standing when Andrew Gibbs replaces this line with "ADOPTED <date>".

Covers WAFR Operational Excellence: *Mechanisms exist to manage responsibilities and ownership*, *Mechanisms exist to request
additions, changes, and exceptions*, *Responsibilities between teams are predefined or negotiated*, *Escalation is
encouraged*, *Communications are timely, clear, and actionable*, *Resource teams appropriately*, *Ensure personnel
capability*, *Team members are encouraged to maintain and grow their skill sets*, *Evaluate internal customer needs*.

## 1. Who owns what

RelayShield LLC has one owner and operator, **Andrew Gibbs**. Claude Code sessions assist with engineering under his
instruction; they hold no standing authority and cannot dispatch workflows or reach AWS.

| Area | Owner | Notes |
|---|---|---|
| Everything: product, AWS account 239677749008, GitHub repository, customer support, billing, security | Andrew Gibbs | single point of failure, accepted and stated |
| Engineering changes | Andrew Gibbs, drafted by Claude sessions | every change is a commit on a branch; merging is his act |
| Deploys | Andrew Gibbs | workflow dispatch is a human click; the deploy role is OIDC only |
| Backup of the owner's access (second person who can act if the owner cannot) | CONFIRM: is there one? | if none, record that as an accepted risk; see `docs/reliability/recovery_objectives_and_dr_plan.md` |

Ownership is recorded in this file and in the Owner line of each runbook (`relayshield_incident_response_plan.md` names the
owner, for example). The repository's `CLAUDE.md` is the standing set of rules every session must follow.

## 2. How a change, an addition or an exception is requested

- **Change or addition:** an instruction from the owner in a session, or a GitHub issue. It lands as a commit on a
  `claude/*` branch, tested (`tests.yml` runs on every pull request and gates deploys), merged by the owner.
- **Exception to a standing rule:** only the owner can grant one, and it is recorded in `docs/claude_memory/LOG_CURRENT.md`
  with the date and the reason, never given silently. Several standing rules in `CLAUDE.md` exist because an exception was
  made once and cost a round.
- **Request from a customer or partner:** arrives by email or the Telegram bot and is triaged by the owner. CONFIRM the
  actual intake channels and the target response time.

## 3. Escalation

There is no team to escalate to, so escalation here means the owner reaching outside for help, without delay and without
embarrassment:

| Situation | Escalate to | When |
|---|---|---|
| AWS service problem or account issue | AWS Support, once a support plan exists (a decision for the owner) | any production-impacting AWS fault |
| Suspected security incident | follow `relayshield_incident_response_plan.md` | immediately |
| Payment problem | Stripe support | any failed payout or webhook outage |
| Anything the owner is unsure about | stop and ask before acting on production | always |

CONFIRM: names and contact routes for any trusted second person (adviser, contractor) who may be called.

## 4. Communications

- **Customers:** incidents affecting customers are communicated by email and the Telegram bot as soon as the scope is
  known, saying what happened, what was affected, and what is being done. CONFIRM the channel order and who sends.
- **Internal record:** every session writes its state to `docs/claude_memory/LOG_CURRENT.md` before it ends, so the next
  session and the owner can see it. The "WHERE ... LEFT THINGS" section is the handoff.
- **Alarms:** CloudWatch alarms notify the SNS target the existing Lambda error alarms use. An alarm nobody reads is not a
  control; `docs/reliability/game_day_plan.md` scenario 4 tests the path.

## 5. Skills and capacity

A one-person operation depends on the owner's skills and on tools that remove repeated manual work. What exists:
committed runbooks and diagnostic scripts per failure class, dry-run-default tools with tests, a CI test gate, and drift
checks. CONFIRM what the owner does to keep current on AWS and security practice (courses, AWS Skill Builder, reading); a
line stating what is actually done is more credible than a plan.
Capacity: the constraint is the owner's time. Work that can be automated, tested and left alone is preferred to work that
needs attention; the WAFR remediation follows that rule.

## 6. Customer needs

Customer needs are evaluated through usage data (the funnel and telemetry tables), support contacts, and the partner and
marketplace feedback channels. CONFIRM the cadence at which the owner reviews them.
