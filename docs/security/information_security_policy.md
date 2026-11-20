# RelayShield Information Security Policy

**STATUS: DRAFT, written 2026-11-20 by Claude from the repository. NOT ADOPTED.**
It becomes the standing policy when Andrew Gibbs replaces this line with `ADOPTED <date>`.
Every statement marked **CONFIRM** is something only the owner can state truthfully; resolve or delete each one before
adopting. A statement with no CONFIRM was read from code or a committed document, and the source is named in Section 14.

| | |
|---|---|
| **Organization** | RelayShield LLC, Massachusetts, United States |
| **Policy owner** | Andrew Gibbs, Founder |
| **Version** | 0.1 (draft) |
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
decisions and recovery. Sections 11 and 14 record how that is managed and what remains a gap.

## 3. Roles and responsibilities

| Role | Held by | Responsibility |
|---|---|---|
| Policy owner, Incident Commander, system owner | Andrew Gibbs | Adopts and reviews this policy; approves every production change; owns incident response |
| Engineering assistant | Claude Code sessions | Drafts changes as commits on a branch. Cannot merge, deploy, or reach AWS. Merging and deploying are the owner's acts |
| Backup of the owner's access | **CONFIRM: is there a second person who can act if the owner cannot?** | If none, record it as an accepted risk in Section 14 |

## 4. Data classification and handling

| Class | Examples | Handling |
|---|---|---|
| **Customer personal data** | Phone numbers and email addresses of monitored subscribers | Phone and email are field-encrypted with AWS KMS. Exposed data is ciphertext without the key. Never written to logs in the clear |
| **Customer proxy traffic metadata** | Tool-call audit entries from the MCP Proxy Firewall | Audit entries store a SHA-256 hash of the arguments, never the raw arguments. Matched PII and credential values found while screening are never logged or returned; verdicts carry pattern types and counts only |
| **Secrets and keys** | Signing keys, API keys, per-tenant proxy tokens, license keys | Held in AWS Secrets Manager. Never logged, never committed (Section 7) |
| **Payment data** | Card details | Not held by RelayShield. Payments are processed by Stripe |
| **Public or internal business data** | Marketing copy, threat-intelligence corpus, internal documents | Internal documents live in the private repository and private Drive |

Principles that apply to every class:

1. **Collect the minimum.** The product does not need customer network access, endpoint agents or privileged credentials
   to customer infrastructure, and does not take them.
2. **No third-party telemetry by default.** The proxy's telemetry is off unless the customer sets it. At either level
   it never sends tool arguments, tool names, agent identities, client IPs, response text or audit entries.
3. **Redaction is available to the customer.** PII redaction in the hosted proxy is opt-in per tenant and, when enabled,
   removes email, phone, SSN, card numbers, API keys or secrets, and crypto wallet addresses from tool calls and tool
   results before they reach the agent or the audit log.
4. **Retention.** **CONFIRM: state the retention period for audit logs, subscriber records and tenant records, and the
   deletion procedure on termination.** (The provisioning code does tear down a tenant's instance, address, DNS record
   and secret on termination.)

## 5. Access control

1. **Least privilege.** Each service identity gets only the permissions it needs. Moving each Lambda function onto its
   own IAM role, in place of one shared role, is under way and is tracked in `iam_role_split.md`. Until it is finished,
   the shared role is a known weakness (Section 14).
2. **No long-lived deploy credentials.** Production deployments authenticate through GitHub OIDC to a dedicated deploy
   role. There is no stored AWS access key for deployment.
3. **Human approval for production.** Workflow dispatch is a human action. Claude sessions cannot trigger it.
4. **Multi-factor authentication.** **CONFIRM: MFA is enforced on the AWS root account and IAM users, GitHub, Cloudflare,
   Stripe, and the Google account that owns the company mailbox.**
5. **Tenant console.** Each hosted customer receives a tenant-scoped console login. Setup is by a single-use link, valid
   72 hours, sent to the Stripe customer email. Billing is read-only. Tenant proxy tokens can be rotated by the tenant.
   Credentials selected for a tenant's upstream servers are chosen by the session's tenant; a credential never resolves
   a tenant.
6. **Roles.** API keys carry a role of `admin`, `operator` or `viewer`, and billing is per customer, not per key.
   **CONFIRM: what each role may do in the tenant console, and that the console enforces it.** See Section 14: the
   source comment on the console's admin API says its authentication is a preview stub with role enforcement still to be
   built.
7. **Status log.** **CONFIRM: the status log is gated by Cloudflare Access, and by which identities.** This was asserted
   by the owner and could not be verified from the repository.
8. **Access review.** The owner reviews IAM users, roles, GitHub collaborators and Cloudflare tokens at each annual
   review and after any incident. **CONFIRM that this is done.**

## 6. Tenant isolation (hosted MCP Proxy Firewall)

Each paying tenant of the hosted proxy gets its own virtual machine. There is no pooling of tenants on shared proxy
processes. Specifically, from the provisioning code:

- One dedicated instance per tenant, launched by the Stripe webhook after signature verification. The webhook never
  provisions inline.
- Its own Elastic IP and its own DNS name, `<tenant-id>.proxy.relayshield.net`.
- Its own secret in AWS Secrets Manager (`relayshield/hosted/<tenant-id>`) holding that tenant's proxy token and license
  key.
- TLS terminated on the instance (Caddy, with certificates from a public certificate authority).
- A signed license (Ed25519) bound to the plan.
- Provisioning is idempotent: a conditional database write means two concurrent requests cannot launch two instances.
- Termination tears down the instance, address, DNS record, secret and status record. A daily sweep completes any
  termination that has passed its deadline.

**CONFIRM before relying on the next three lines:** the security group's inbound rules, whether instance volumes are
encrypted, and whether the instance metadata service requires tokens (IMDSv2). The provisioning code references a
security group and an instance profile but this document has not read their settings.

**Vultr deployment: CONFIRM.** The current build provisions on AWS. If the Vultr marketplace app runs the proxy on
Vultr infrastructure, state here which of the above carry over, who administers the Vultr account and how the account
is protected.

## 7. Cryptography and secrets management

1. Data in transit to customers is protected by TLS.
2. Customer phone numbers and email addresses are encrypted at rest with AWS KMS.
3. Proxy verdicts are signed with Ed25519, so a customer or partner can verify a decision. The signing key comes only
   from configuration, is never logged, and verdicts are explicitly marked unsigned if no key is present.
4. The proxy's audit log is append-only and hash-chained. Each entry commits to the one before it, and a verification
   routine walks the chain and reports where tampering occurred.
5. Secrets live in AWS Secrets Manager. They are not committed to the repository. A scanner (Gitleaks) runs in CI on
   every push to `main` and every pull request to `main`. The policy for any vendor documentation that may contain personalized credentials is: read it before
   pasting it anywhere.
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

- AWS CloudTrail records AWS API calls. AWS Config records configuration changes. CloudWatch alarms cover Lambda errors,
  database throttling and API gateway error spikes, and notify the owner by email. **CONFIRM that each is enabled in the
  production account today; the incident plan states them as detection sources.**
- Every proxied call emits a structured log line without raw arguments.
- Incidents are recorded in a status log with root cause and fix.

## 10. Vulnerability and incident management

1. Security incidents are handled under `relayshield_incident_response_plan.md`: severity P1 to P4, target response
   from 1 hour to 72 hours, containment, eradication, recovery, and a written post-incident review within 5 business days
   of a P1 or P2.
2. Customers are notified of a confirmed exposure of their personal data within 72 hours of confirmation, and of a
   service outage longer than 4 hours.
3. Dependency and code vulnerabilities found by the CI checks are triaged by severity. **CONFIRM a target time to
   remediate High and Critical findings; none is stated today.**
4. **CONFIRM a published way to report a vulnerability to RelayShield** (an address and an expected response time).

## 11. Business continuity and disaster recovery

Recovery objectives and the disaster recovery plan are drafted in `docs/reliability/recovery_objectives_and_dr_plan.md`
and are **not yet adopted**; no recovery time or availability figure in them is a commitment until the owner adopts it.
The incident plan relies on point-in-time recovery for the database. **CONFIRM it is enabled on every production
table.** The single-operator dependency is addressed in Section 3.

## 12. Third parties and sub-processors

RelayShield uses a small set of infrastructure and service providers. Each is selected for its own security program
and is reviewed when its role changes.

| Provider | Role |
|---|---|
| Amazon Web Services | Compute, data storage, key management, secrets, email delivery for the hosted proxy |
| Cloudflare | DNS, edge workers, and key-value display cache for the tenant console |
| Stripe | Payment processing and subscription billing |
| Messaging and carrier providers | Alert delivery and carrier lookups for the consumer product |
| Third-party data providers | Breach and threat-intelligence lookups; some lookups send a typed value to a provider |

Customers are told when a check sends their typed value to a third party. The AWS-licensed product path makes no
third-party calls by design. **CONFIRM the Vultr account as a sub-processor if the marketplace app runs there.**

## 13. Personnel and the use of AI assistants

There are no employees or contractors today. If one is added, they receive named accounts, least privilege, MFA, and
sign confidentiality terms before access, and access is removed the day they leave. Claude Code sessions work on
branches, never hold production credentials, and their output is reviewed by the owner before it is merged.

## 14. Evidence, known gaps and exceptions

### Where each statement was verified

| Statement | Source |
|---|---|
| Dedicated instance, address, DNS, secret and license per tenant; idempotent; termination | `relayshield_hosted_provision.py` |
| Tenant-scoped console, one-time 72-hour setup link, read-only billing, token rotation | `relayshield_hosted_provision.py`; `cloudflare_worker_landing.js` release notes |
| Opt-in PII redaction, off by default | `mcp_proxy/README.md`; `cloudflare_worker_landing.js` release notes |
| Hash-chained audit log, argument hash only | `mcp_proxy/audit.py` |
| Signed verdicts, secrets never logged | `mcp_proxy/README.md`; `mcp_proxy/verdicts.py` |
| Telemetry off by default and what it never sends | `mcp_proxy/README.md` |
| Per-tenant credentials store | `mcp_proxy/tenant_secrets.py` |
| Incident procedures, notification windows | `relayshield_incident_response_plan.md` |
| CI security scans | `.github/workflows/security_audit.yml` |

### Known gaps, stated openly

1. **This policy is a draft until adopted.** Until then, no survey or questionnaire should state that a policy is
   adopted.
2. **Role enforcement in the tenant console is not proven.** The admin API's source says its authentication is a preview
   stub with RBAC still to be built.
3. **Access gating on the status log is unverified** from the repository.
4. **The shared IAM role still carries many policies.** The per-function split is in progress.
5. **No SOC 2 or ISO 27001 certification.** RelayShield instead uses the AWS Well-Architected Framework Review as its
   independent-style evidence, and that review is not complete.
6. **No third-party penetration test** is recorded. **CONFIRM.**
7. **Single operator.** Loss of the owner's access halts the company. See Section 3.
8. **Recovery documents are drafts**, and no availability figure is committed.

### Exceptions

An exception to this policy requires the owner's written approval recorded in the repository, with a reason and an expiry
date. No exception is recorded today.

## 15. Enforcement and review

Violation of this policy by anyone with access is grounds for immediate removal of that access. The owner reviews this
policy annually and after any P1 or P2 incident, records the review date and changes at the top of this file, and keeps
prior versions in git history.
