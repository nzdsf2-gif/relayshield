# RelayShield Information Security Policy

**STATUS: ADOPTED 2026-11-20** by Andrew Gibbs, Founder and policy owner.

| | |
|---|---|
| **Organization** | RelayShield LLC, Massachusetts, United States |
| **Policy owner** | Andrew Gibbs, Founder |
| **Version** | 1.0 |
| **Adopted** | 2026-11-20 |
| **Review cycle** | Annually, and after any declared P1 or P2 incident |
| **Applies to** | RelayShield LLC, every RelayShield product (including the hosted MCP Proxy Firewall), every system that stores or processes customer data, and every person or automated agent with access to them |
| **Related documents** | `relayshield_incident_response_plan.md` (adopted, v1.0); `docs/ops/operating_model.md` (draft); `docs/reliability/recovery_objectives_and_dr_plan.md` (draft); Privacy Policy; Terms of Service |

---

## 1. Purpose

This policy states how RelayShield protects the confidentiality, integrity and availability of its systems and of the
data customers entrust to it. RelayShield sells security products. Customers and marketplace partners are entitled to
ask whether the company holds itself to the standard it sells, and this document is the written answer.

## 2. Scope and company profile

RelayShield is a sole-founder company. There are no employees. One person owns product, infrastructure, security,
support and billing, and says so rather than describing a team that does not exist. Claude Code sessions assist with
engineering under the founder's direction. They hold no standing authority, have no AWS credentials, and cannot dispatch
deployment workflows.

This has a security consequence that the policy states plainly: the owner is a single point of failure for access,
decisions and recovery. Sections 3 and 14 record this as an accepted risk.

## 3. Roles and responsibilities

| Role | Held by | Responsibility |
|---|---|---|
| Policy owner, Incident Commander, system owner | Andrew Gibbs | Adopts and reviews this policy; approves every production change; owns incident response |
| Engineering assistant | Claude Code sessions | Drafts changes as commits on a branch. Cannot merge, deploy, or reach AWS. Merging and deploying are the owner's acts |
| Backup of the owner's access | None | There is no second person who can act if the owner cannot. This is an accepted risk (Section 14) |

## 4. Data classification and handling

| Class | Examples | Handling |
|---|---|---|
| **Customer personal data** | Phone numbers and email addresses of monitored subscribers | Phone and email are field-encrypted with AWS KMS. Exposed data is ciphertext without the key. Never written to logs in the clear |
| **Customer proxy traffic metadata** | Tool-call audit entries from the MCP Proxy Firewall | Audit entries store a SHA-256 hash of the arguments, never the raw arguments. Matched PII and credential values found while screening are never logged or returned; verdicts carry pattern types and counts only |
| **Secrets and keys** | Signing keys, API keys, per-tenant proxy tokens, license keys | Held in AWS Secrets Manager. Never logged, never committed (Section 7) |
| **Payment data** | Card details | Not held by RelayShield. Payments are processed by Stripe |
| **Public or internal business data** | Marketing copy, threat-intelligence corpus, internal documents | Internal documents live in private repositories and a private drive |

Principles that apply to every class:

1. **Collect the minimum.** The product does not need customer network access, endpoint agents or privileged credentials
   to customer infrastructure, and does not take them.
2. **No third-party telemetry by default.** The proxy's telemetry is off unless the customer sets it. At either level
   it never sends tool arguments, tool names, agent identities, client IPs, response text or audit entries.
3. **Redaction is available to the customer.** PII redaction in the hosted proxy is opt-in per tenant and, when enabled,
   removes email, phone, SSN, card numbers, API keys or secrets, and crypto wallet addresses from tool calls and tool
   results before they reach the agent or the audit log.
4. **Retention.** Audit logs, tenant records and subscriber records are retained for one year and then deleted. On
   termination of a hosted tenant, its instance, address, DNS record and secret are removed immediately; its records
   follow the one-year retention.

## 5. Access control

1. **Least privilege.** Each service identity gets only the permissions it needs. Moving each Lambda function onto its
   own IAM role, in place of one shared role, is under way. Until it is finished, the shared role is a known weakness
   (Section 14).
2. **No long-lived deploy credentials.** Production deployments authenticate through GitHub OIDC to a dedicated deploy
   role. There is no stored AWS access key for deployment.
3. **Human approval for production.** Workflow dispatch is a human action. Claude sessions cannot trigger it.
4. **Multi-factor authentication** is enforced on the AWS root account and IAM users, GitHub, Cloudflare, Stripe, and
   the account that owns the company mailbox.
5. **Tenant console.** Each hosted customer receives a tenant-scoped console login. Setup is by a single-use link, valid
   72 hours, sent to the Stripe customer email. Billing is read-only. Tenant proxy tokens can be rotated by the tenant.
   Credentials used to reach a tenant's upstream servers are selected by the session's tenant; a credential never
   resolves a tenant.
6. **Roles.** Per-tenant role-based access controls operate in the production MCP Proxy Firewall console:

   | Role | Scope | Access |
   |---|---|---|
   | `founder` | All tenants | Read and write |
   | `msp_admin` | Child tenants of the user's own MSP | Read and write |
   | `client_admin` | Own tenant only | Read and write |
   | `operator` | Own tenant or MSP scope | Read-only |
   | `viewer` | Own tenant or MSP scope | Read-only |

   The administrative API is separate from the tenant console. Role enforcement for its provisioning routes exists as
   a staged module that is not yet deployed, and the API's authentication is a preview stub with role enforcement still
   to be built. This is a known gap (Section 14).
7. **Status log.** The status log at `api.relayshield.net/status` is gated by Cloudflare Access with one-time PIN
   login. Access is limited to the owner and named reviewers by policy, and was confirmed working on 2026-11-19.
8. **Access review.** The owner reviews IAM users, roles, GitHub collaborators and Cloudflare tokens at each annual
   review and after any incident.

## 6. Tenant isolation (hosted MCP Proxy Firewall)

Each paying tenant of the hosted proxy gets its own virtual machine. There is no pooling of tenants on shared proxy
processes. Specifically, from the provisioning code:

- One dedicated instance per tenant, launched by the Stripe webhook after signature verification. The webhook never
  provisions inline.
- Its own Elastic IP and its own DNS name, `<tenant-id>.proxy.relayshield.net`.
- Its own secret in AWS Secrets Manager (`relayshield/hosted/<tenant-id>`) holding that tenant's proxy token and license
  key.
- Network access restricted by a security group.
- TLS terminated on the instance (Caddy, with certificates from a public certificate authority).
- A signed license (Ed25519) bound to the plan.
- Provisioning is idempotent: a conditional database write means two concurrent requests cannot launch two instances.
- Termination tears down the instance, address, DNS record, secret and status record. A daily sweep completes any
  termination that has passed its deadline.

**Hosting and portability.** Production hosting today is per-tenant AWS EC2 instances. A QCOW2 image package of the
per-tenant dataplane gateway has been built so the same per-tenant model can be deployed through the Vultr
marketplace. Isolation is by dedicated virtual machine in both cases.

## 7. Cryptography and secrets management

1. Data in transit to customers is protected by TLS.
2. Customer phone numbers and email addresses are encrypted at rest with AWS KMS.
3. Proxy verdicts are signed with Ed25519, so a customer or partner can verify a decision. The signing key comes only
   from configuration, is never logged, and verdicts are explicitly marked unsigned if no key is present.
4. The proxy's audit log is append-only and hash-chained. Each entry commits to the one before it, and a verification
   routine walks the chain and reports where tampering occurred.
5. Secrets live in AWS Secrets Manager. They are not committed to the repository. A scanner (Gitleaks) runs in CI on
   every push to `main` and every pull request to `main`. Vendor documentation that may contain personalized
   credentials is read before it is pasted anywhere.
6. Secrets are rotated after any suspected exposure, and the incident plan lists exactly which ones.

## 8. Secure development and change management

1. **Every change is a commit on a branch.** Nothing is edited on a live system as the record of the change.
2. **Production deploys come from the repository.** The "drift rule" applies: anything not in the repository is erased
   by the next deploy, so live artifacts are recovered into git first. A scheduled drift check reports differences
   between deployed functions and the repository.
3. **Automated checks.** On every push to `main` and every pull request to `main`, a security audit workflow runs static
   analysis (Bandit, failing the build on high-severity findings), a dependency vulnerability check (pip-audit) and a
   full-history secret scan (Gitleaks). A separate workflow runs the test suite. Workflow files are validated after every
   edit, because a workflow that cannot be parsed fails silently.
4. **Payment paths are changed with extra care.** A change to the Stripe webhook or any payment path is pinned by tests
   first and ships behind a flag that is off at deploy.
5. **Tests prove the real behavior.** Code that parses a library's output is checked against that library's real output,
   not against input written by the same hand as the code.
6. **Rollback.** A rollback workflow publishes a prior known-good version of a function.
7. **Proxy outbound calls.** Where a product commits that a path makes no third-party calls (the AWS-licensed path), a
   new outbound lookup must honor that flag in the same commit, with a test that fails if it runs.

## 9. Logging and monitoring

Detection sources, as recorded from the AWS production account:

| Source | Status |
|---|---|
| AWS CloudTrail | Enabled; recorded complete in the company task log. Records AWS API calls |
| AWS Config | One configuration recorder, confirmed in the October 2026 Well-Architected evidence run. Records configuration changes |
| Amazon CloudWatch alarms | Five alarms on Lambda errors (breach monitor, intel monitor, SIM swap monitor, Stripe webhook, WhatsApp webhook), none in alarm, as of 2026-10-11. The incident response plan routes alarms to the owner's email |
| Application logs | Structured log line for every proxied call, without raw arguments |
| Status log | Incident record with root cause and fix |

Coverage is being extended under the Well-Architected remediation: alarms on API gateway errors and throttles, a service
quota alarm, and an alarm on the asynchronous-failure queue exist as repeatable, dry-run-by-default tooling and are
applied one step at a time by the owner. Until each is applied it is a known gap (Section 14). The read-only evidence
script `tools/wafr_evidence.sh` reports the live state of each source above, and its output is attached to the annual
review.

## 10. Vulnerability and incident management

1. **Incidents** are handled under `relayshield_incident_response_plan.md`: severity P1 to P4, containment,
   eradication, recovery, and a written post-incident review within 5 business days of a P1 or P2. For security
   incidents, target response runs from 1 hour (P1) to 72 hours (P4), and target resolution from 4 hours (P1) to 2 weeks
   (P4).
2. **Customer notification.** Customers are notified of a confirmed exposure of their personal data within 72 hours of
   confirmation, and of a service outage longer than 4 hours.
3. **Response commitment.** RelayShield aims to respond to any security report or inquiry within one business day.
4. **Vulnerability reporting approach.**
   1. *Where to report.* Email relayshieldadmin@gmail.com with the subject "Security report". Include the affected
      asset, the steps to reproduce, and the impact. Do not include customer data in the report.
   2. *Acknowledgement.* The owner acknowledges within one business day.
   3. *Triage.* The owner reproduces the issue and assigns a severity using the incident plan's P1 to P4 scale. A flaw
      that exposes customer data or gives unauthorized production access is P1.
   4. *Remediation targets.* The incident plan's target resolution times apply: P1 4 hours, P2 24 hours, P3 72 hours,
      P4 2 weeks. The reporter is told the severity and the expected fix date.
   5. *Fix and verify.* The fix ships through the normal pipeline (Section 8) with a test that fails without it.
      Affected customers are notified under item 2.
   6. *Closure.* The reporter is told when the fix is live and, with their permission, credited. RelayShield does not
      run a paid bug bounty.
   7. *Good-faith testing.* Researchers who test only their own tenant, access no one else's data, do not degrade the
      service, and do not use social engineering will not be pursued for that testing.
   8. *Internal findings.* Findings from the CI checks in Section 8 follow the same severity scale and targets. A
      high-severity static analysis finding or a known vulnerable dependency fails the build and blocks the merge.

## 11. Business continuity and disaster recovery

Recovery for the database relies on DynamoDB point-in-time recovery, which restores to any second in the previous 35
days, with the latest restorable point about 5 minutes behind. The company strategy record states point-in-time recovery
is on for all tables. The recovery plan records that the protection script's run status and a restore test have not yet
been evidenced: both are scheduled (game day 1) and the plan lists a recurring backup plan beyond the 35-day window as
not yet built. Compute is re-created from the repository by the deployment pipeline. The recovery objectives and
disaster recovery plan are in `docs/reliability/recovery_objectives_and_dr_plan.md` and are not yet adopted, so no
recovery time or availability figure in them is a commitment. The single-operator dependency is addressed in Section 3.

## 12. Third parties and sub-processors

RelayShield uses a small set of infrastructure and service providers. Each is selected for its own security program
and is reviewed when its role changes.

| Provider | Role |
|---|---|
| Amazon Web Services | Compute, data storage, key management, secrets, email delivery for the hosted proxy |
| Cloudflare | DNS, edge workers, access gating for the status log, and key-value display cache for the tenant console |
| Stripe | Payment processing and subscription billing |
| Vultr | Infrastructure on which per-tenant gateways run when deployed through the Vultr marketplace |
| Messaging and carrier providers | Alert delivery and carrier lookups for the consumer product |
| Third-party data providers | Breach and threat-intelligence lookups; some lookups send a typed value to a provider |

Customers are told when a check sends their typed value to a third party. The AWS-licensed product path makes no
third-party calls by design.

## 13. Personnel and the use of AI assistants

There are no employees or contractors today. If one is added, they receive named accounts, least privilege, MFA, and
sign confidentiality terms before access, and access is removed the day they leave. Claude Code sessions work on
branches, never hold production credentials, and their output is reviewed by the owner before it is merged.

## 14. Evidence, known gaps and exceptions

### Where each statement was verified

| Statement | Source |
|---|---|
| Dedicated instance, address, DNS, secret and license per tenant; idempotent; termination | `relayshield_hosted_provision.py` |
| Tenant-scoped console, one-time 72-hour setup link, read-only billing, token rotation | `relayshield_hosted_provision.py`; product release notes |
| Opt-in PII redaction, off by default | `mcp_proxy/README.md`; product release notes |
| Hash-chained audit log, argument hash only | `mcp_proxy/audit.py` |
| Signed verdicts, secrets never logged | `mcp_proxy/README.md`; `mcp_proxy/verdicts.py` |
| Telemetry off by default and what it never sends | `mcp_proxy/README.md` |
| Per-tenant credentials store | `mcp_proxy/tenant_secrets.py` |
| Incident procedures, severity targets, notification windows | `relayshield_incident_response_plan.md` |
| CI security scans | `.github/workflows/security_audit.yml` |
| Alarms, Config recorder, PITR status as recorded | `wafr_answers_reliability_2026-10-11.md`; `docs/reliability/recovery_objectives_and_dr_plan.md`; `tools/wafr_evidence.sh` |
| Status log gated by Cloudflare Access | Owner confirmation, 2026-11-19 |

### Known gaps, stated openly

1. **Administrative API role enforcement.** Enforcement for the provisioning routes exists as a staged module that is
   not yet deployed, and the API's authentication is a preview stub. The tenant console's roles are not affected.
2. **Shared IAM role.** The per-function role split is in progress; the shared role still carries many policies.
3. **No SOC 2 or ISO 27001 certification.** RelayShield uses the AWS Well-Architected Framework Review as its
   independent-style evidence, and that review is not complete.
4. **No third-party penetration test** has been performed.
5. **Single operator.** There is no second person who can act if the owner cannot (Section 3).
6. **Recovery.** The recovery documents are not adopted, a restore test has not yet been run, and there is no recurring
   backup plan beyond the 35-day point-in-time window (Section 11).
7. **Monitoring coverage.** Alarms beyond the five Lambda error alarms are built and awaiting application (Section 9).
8. **Public disclosure page.** The reporting approach in Section 10 is in force. A public security page and a
   `security.txt` file are not yet published.

### Exceptions

An exception to this policy requires the owner's written approval recorded in the repository, with a reason and an expiry
date. No exception is recorded today.

## 15. Enforcement and review

Violation of this policy by anyone with access is grounds for immediate removal of that access. The owner reviews this
policy annually and after any P1 or P2 incident, records the review date and changes at the top of this file, and keeps
prior versions in git history.
