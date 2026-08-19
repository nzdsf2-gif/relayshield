# Palo Alto Tech Alliance application — draft answers

**Read the blocker first.** The form states: *"Due to the current volume of applications, the
requirement is at least 2 joint customers that are willing to use and validate the integration."*
Joint Customer 1 and 2, name **and** contact info, are required fields.

RelayShield does not have two customers who also run Cortex XSOAR and would agree to be named.
Do not invent them — the contacts are contacted, and being caught costs the PR relationship that
is currently the most valuable thing in this account.

**Question to settle before submitting:** the Tech Alliance program is a co-sell partner motion.
The XSOAR pack is a **community contribution** (`support: community`) whose code is already
approved in `demisto/content#45206`. The only thing missing is a tenant to record demo-prep on.
Those may be different doors. Ask before spending the joint-customer requirement on it.

---

## Answers for every other field

**Tell us about your company and products**

> RelayShield is an identity-compromise and agent-security threat intelligence API. We collect
> from criminal Telegram channels, infostealer log markets, breach corpora and certificate
> transparency, and expose the result as per-call endpoints and a TAXII 2.1 feed. Coverage is the
> identity and credential layer rather than the network layer: breach exposure, infostealer
> sessions, SIM-swap signals, lookalike domains, leaked LLM and machine credentials, MCP registry
> risk and supply-chain vendor risk. We are a small independent vendor, distributed through AWS
> Marketplace, n8n, Zapier, Elastic, Rapid7 InsightConnect and Microsoft Sentinel.

**Main product name:** RelayShield Threat Intelligence API

**Integration type:** the XSOAR content pack (choose the content-pack / app option; if the list
only offers API-based integration, that is the closer match).

**1st priority Palo Alto product:** Cortex XSOAR

**Use case and customer pain points**

> A SOC analyst triaging an alert in XSOAR can enrich the infrastructure — the IP, the domain, the
> hash — but not the identity behind it. Whether that user's credentials are already in a stealer
> log, whether their session is live in a criminal market, whether their number was SIM-swapped
> last week, whether the domain in the phish is a registered lookalike of the customer's own: none
> of that is available from the enrichment sources a playbook normally reaches for, so the analyst
> closes the ticket without knowing the account is already owned.
>
> The pack adds six commands usable directly in playbooks: `domain`, `ip` and `email` (each
> setting a DBotScore, so they slot into existing reputation logic unchanged), plus
> `relayshield-mcp-registry-risk`, `relayshield-cert-expiry` and `relayshield-supply-chain`.

**Are there other use cases?** Yes

**Differentiator and value proposition for Palo Alto Networks**

> Two things XSOAR playbooks cannot currently reach. First, the identity and credential layer —
> the signals that precede an intrusion rather than describe one in progress, which is
> complementary to EDR and network telemetry rather than competing with it. Second, agent
> security: MCP registry risk and supply-chain vendor risk are new attack surface as customers
> deploy AI agents, and there is no established enrichment source for it.
>
> Engineering risk to Palo Alto is close to zero: the pack is built, the code is approved in
> demisto/content#45206, it carries the docs-approved label, and it is community-supported, so it
> costs Palo Alto no support burden.

**Timeline to complete:** 30 days from tenant access. The pack is finished; the remaining work is
the demo recording, the Integration Guide and the Joint Solution Brief.

**Budgeted and resourced?** Yes

**Commit to 90 days including Integration Guide and Joint Solution Brief?** Yes

**Has an integration already been done / PoC completed?** Yes — content pack built and submitted as
demisto/content#45206, code approved by the reviewer, docs-approved label applied, currently
labelled pending-demo.

**Do you have a way to track who will use the integration?** Yes — per-API-key usage is recorded
per call, so adoption through the pack is attributable.

**Has an integration with other security vendors in the same space been done before?** Yes:
Rapid7 InsightConnect (plugin submitted as rapid7/insightconnect-plugins#4024), Microsoft Sentinel
(community PR Azure/Azure-Sentinel#14924 plus a published integration guide), Elastic Security
(published integration guide), and a TAXII 2.1 feed that OpenCTI and Sentinel consume natively.

**What do you need from Palo Alto Networks?**

> A Cortex XSOAR tenant to record demo-prep against. That is the entire ask. The pack's code is
> already approved in demisto/content#45206 and the only remaining merge gate is the recorded
> demo, which xsoar.pan.dev requires be performed on an instance carrying the pack. RelayShield
> does not operate an XSOAR tenant and Community Edition is discontinued.

---

## If you decide to pursue the joint customers

Ask Arjen Peirce first — he is a sales consultant with client relationships, and the question is
narrow: does any client of yours run Cortex XSOAR and would they agree to be named as a validating
customer. Two yeses clears the gate honestly. Anything less and the application should wait.
