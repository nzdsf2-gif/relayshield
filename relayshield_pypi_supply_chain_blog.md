# Your AI Stack Just Became a Credential Harvester

## How the 2026 PyPI Supply Chain Crisis Targeted Developers at Scale — and What to Do About It

If you run AI agents, use LiteLLM to route model calls, or build on any Python-based AI framework, you need to read this. In March and April 2026, attackers didn't try to break into developer environments directly. They compromised the packages developers trust unconditionally — and turned those packages into credential harvesters running silently inside developer machines and CI/CD pipelines.

This wasn't opportunistic. It was surgical.

---

## What Happened

### The TeamPCP Campaign (March 2026)

A threat actor group — now tracked as TeamPCP — began their campaign not on PyPI, but in GitHub Actions. They identified a misconfigured `pull_request_target` workflow in Trivy, a widely-used open source security scanner, and used it to steal a personal access token. That single token gave them the ability to push malicious commits to 76 of 77 Trivy GitHub Action version tags.

From there, the compromised Trivy action became the key to everything else. Any project using Trivy in its CI pipeline was now running attacker-controlled code with access to that pipeline's secrets.

### LiteLLM — 3.4 Million Downloads Per Day Compromised (March 24, 2026)

LiteLLM is the package that routes API calls across OpenAI, Anthropic, Google, and dozens of other model providers. If you build AI agents, there's a reasonable chance LiteLLM is in your stack.

On March 24, versions 1.82.7 and 1.82.8 were published to PyPI with malicious code embedded. The attacker had hijacked the maintainer's account and bypassed standard GitHub release protocols to push directly to PyPI — skipping code review entirely.

The malicious code did one thing: it harvested secrets. Environment variables, API keys, cloud credentials, SSH keys, Kubernetes configs, Docker configurations, shell history, database credentials, and CI/CD pipeline secrets — all exfiltrated silently on install.

### Telnyx (March 27, 2026)

Three days later, the Telnyx Python SDK — versions 4.87.1 and 4.87.2 — was backdoored using the same technique. Telnyx is a telecom API provider. Developers using it for SMS, voice, or SIM-based authentication suddenly had their credentials in attacker hands.

### PyTorch Lightning (April 30, 2026)

The campaign continued. Versions 2.6.2 and 2.6.3 of PyTorch Lightning were published containing embedded credential theft code. The malware gathered credentials and then published additional infected package versions — a self-propagating supply chain attack designed to spread laterally to downstream projects.

### Elementary-Data (May 2026)

Version 0.23.3 of the popular data pipeline package was compromised to target developer credentials and cryptocurrency wallets.

---

## The Architecture of the Attack

What makes this campaign significant isn't the volume — it's the targeting.

**The attackers went after AI infrastructure packages specifically.** LiteLLM, Lightning, Telnyx — these are packages that live deep in AI developer stacks. Developers who use them typically also have: Anthropic API keys, OpenAI API keys, AWS credentials, cloud database connections, and CI/CD pipeline tokens worth far more than any individual credential.

The attack chain worked like this:

1. **Compromise a trusted CI tool** (Trivy via GitHub Actions misconfiguration)
2. **Use that foothold to steal a maintainer token**
3. **Push a malicious package version** directly to PyPI, bypassing code review
4. **Harvest environment variables on install** — every machine that ran `pip install` during the window was exfiltrated
5. **Propagate** — some packages then published additional infected versions from the compromised environment

The average developer has no visibility into step 4. The package installs. The build succeeds. The secrets are gone.

---

## Why This Is the Identity Attack Surface You're Not Watching

Traditional identity protection focuses on human credentials — email addresses, passwords, phone numbers. But modern developers are surrounded by non-human credentials: API keys, OAuth tokens, service account secrets, CI/CD pipeline variables.

These credentials don't get MFA. They don't get breach notifications. They don't expire unless you rotate them manually. And when they're harvested through a supply chain attack, there's no login event to alert on — just a silent `pip install` followed by an HTTP request to an attacker-controlled server.

The attack surface has expanded far beyond the developer's own accounts. It now includes every dependency they install.

---

## What Developers Should Do Right Now

### 1. Audit your installed package versions
If you installed LiteLLM between March 24–25, Telnyx between March 27–28, or PyTorch Lightning on April 30–May 1, assume your environment variables were exfiltrated. Rotate every secret in your environment.

### 2. Pin your dependencies
`pip install litellm` installs the latest version automatically. `pip install litellm==1.82.6` pins to a known-good version. Use `pip freeze` to lock your environment and review upgrades before applying them.

### 3. Audit your GitHub Actions workflows for `pull_request_target`
The TeamPCP campaign began with a single misconfigured workflow. The `pull_request_target` trigger runs with elevated permissions and can expose repository secrets to pull requests from forks. If you use it, review it now.

### 4. Use project-scoped PyPI tokens, not account-wide tokens
If your PyPI publishing token covers your entire account, a single leak compromises every package you publish. Scope tokens to individual projects. Rotate them after every major release.

### 5. Enable PyPI Trusted Publishing
PyPI now supports OIDC-based Trusted Publishing — your CI pipeline authenticates using a short-lived token tied to your GitHub repository, with no stored API keys at all. This eliminates the token theft vector entirely.

### 6. Treat your AI API keys like root credentials
Your Anthropic key, OpenAI key, and cloud provider keys should be treated with the same discipline as AWS root credentials: stored in secrets managers, never in `.env` files committed to repos, rotated on a schedule, and monitored for anomalous usage.

---

## The Bigger Pattern

This campaign reflects a structural shift in how attackers approach developer environments. Direct attacks — phishing, credential stuffing, brute force — are increasingly difficult against developers who use password managers, MFA, and hardware keys.

Supply chain attacks bypass all of that. The developer never made a mistake. They installed a package they'd been using for months. The package had a three-day window of malicious versions. The developer's environment was compromised before any security tool fired.

As AI stacks grow in complexity — more packages, more integrations, more API keys in more places — the supply chain attack surface grows with them. LiteLLM being downloaded 3.4 million times per day isn't just a measure of its popularity. It's a measure of the blast radius when it's compromised.

Protecting developer identity now means protecting the entire dependency chain, not just the developer's own credentials.

---

*RelayShield monitors breach exposure, SIM swap attacks, domain lookalikes, and supply chain intelligence for developers and security teams. The B2A API is available at [rapidapi.com/relayshield/relayshield-security-intelligence](https://rapidapi.com/relayshield/relayshield-security-intelligence). The MCP server for Claude integration is available at [pypi.org/project/relayshield-mcp](https://pypi.org/project/relayshield-mcp).*
