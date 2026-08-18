# AWS Partner/ISV Outreach — AgentCore Payments Early Adopter Story

Final, plain-text-safe version (no headers, no em-dashes, no apostrophes, no "Bundle D" internal naming, no bare clickable URLs) for pasting directly into the AWS Partner Central support case Description field.

---

RelayShield is a B2B threat intelligence engine for MSPs, MSSPs, and enterprise SOCs, delivered as a REST API with a 2M+ IOC corpus, 37+ monitored criminal Telegram channels, and 4,500+ tracked malware families. We are an active AWS Marketplace seller. Our threat intelligence API has been publicly listed since June 2026 at $499/mo and $999/mo tiers, and we are finishing a second listing focused on AI agent security: endpoints built to detect exploitation of AI agent infrastructure such as malicious MCP servers, prompt injection breaches, agent framework CVEs, and per agent identity risk scoring for organizations governing AI agent fleets.

We wanted to prove that an autonomous AI agent could genuinely discover and pay for one of our real live API endpoints, not a sandboxed demo, using real infrastructure and real money. We built this entirely on AWS native tooling. We configured AgentCore Gateway with the CDP x402 Bazaar as a native MCP server target at api.cdp.coinbase.com/platform/v2/x402/discovery/mcp, requiring zero custom discovery code, since our endpoints are already indexed in that same Bazaar. We provisioned AgentCore Payments, still in Preview, including a credential provider, payment manager, connector, and an embedded CDP wallet, all via boto3. We ran a Strands agent on Bedrock Claude Sonnet using the official AgentCorePaymentsPlugin for fully automatic 402 handling, with no custom payment client needed.

We funded the embedded wallet with 1 dollar in real USDC on Base mainnet. The agent autonomously searched the Bazaar, found our identity risk score endpoint, signed a payment via CDP delegated signing, and settled it on chain. The transaction hash is 0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016 on Base mainnet, verified via direct RPC with status success. The agent then received and correctly summarized the real scored result.

As far as we can tell this is a genuine, very early real world integration of AgentCore Payments with a live third party AWS Marketplace SaaS product, built during Preview end to end, with real settlement, not a testnet demo.

We would like to connect with whoever on the AgentCore product team or AWS Partner org would be interested in an early adopter story, and get guidance on our path toward ISV Accelerate. We have completed Partner Central identity and business verification and are still building the opportunity and revenue history the program requires. Happy to share full technical detail, a demo, or be a reference customer.

AWS account 239677749008. Live Marketplace listing product ID prod-kb3ftelx44wlk.

---

## Supporting facts
- AWS account: 239677749008
- Live Marketplace listing (TI API): product ID prod-kb3ftelx44wlk
- On-chain proof tx: 0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016 on Base (look up on basescan.org)
