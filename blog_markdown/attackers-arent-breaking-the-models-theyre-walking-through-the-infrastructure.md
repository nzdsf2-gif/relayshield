---
title: "Attackers Aren't Breaking the Models. They're Walking Through the Infrastructure."
slug: attackers-arent-breaking-the-models-theyre-walking-through-the-infrastructure
date: 2026-10-22
---

# Attackers Aren't Breaking the Models. They're Walking Through the Infrastructure.

TrendAI's 1H 2026 State of AI Security report has a finding that should reframe how we think about AI security: attackers are going after the infrastructure around models, not the models themselves.

In a single scan, they found 1,467 exposed MCP servers. And nearly half of the 19,000 MCP server repositories they reviewed tell developers to store credentials in plaintext .env files or config.

## The pattern keeps repeating

This is the fourth independent report in a week landing on the same point:

- **OX Security** scanned 15,465 publicly indexed MCP servers and found home machines exposed through consumer tunnels. Anthropic confirmed the STDIO command injection flaw is "by design."
- **ClawSecure** measured 17 of 20 obfuscation techniques surviving the MCP round trip intact. The best-defended model still obeyed hidden attacker commands 26.7% of the time.
- **TrendAI** found 1,467 exposed MCP servers in one scan, with half the ecosystem's repos normalizing plaintext credential storage.
- **JFrog** has now extended shadow AI detection to developer workstations, because MCP servers, skills, and plugins are landing on laptops directly, including ones that arrive through Git, Slack, or a zip file.

Nobody is breaking the model weights. They're not jailbreaking the frontier labs. They're finding the MCP server someone left exposed, reading the .env file the README told them to create, and walking in.

## The .env problem

The plaintext credential finding deserves emphasis. When half of 19,000 repositories tell developers to put secrets in an unencrypted file, that's not a developer education problem. That's an ecosystem design problem.

The MCP spec doesn't mandate a secrets management story. So every server author invents their own, and the path of least resistance is a .env file sitting next to the code. It works. It's also the first thing an attacker reads when they find the exposed server.

## The shadow problem: servers nobody deployed

The JFrog move names the other half of this. Exposed-server scans only find servers that touch the public internet. The workstation fleet is invisible to them.

A developer installs an MCP server from a GitHub repo a teammate dropped in Slack. It never goes through procurement, never lands in a central inventory, and never gets reviewed. It holds the same plaintext credentials as everything else, it can read the same filesystem, and it phones the same network. Shadow AI is not a separate problem from the exposed-server problem. It is the same problem, one step earlier, on machines nobody is watching.

Inventory is the necessary first step, and it is not a verdict. Knowing a server exists on a laptop does not tell you whether its tools are poisoned, whether its endpoints appear in threat intelligence, or what it actually does at runtime. That gap is why a workstation scan has to pair with screening: inventory the servers, flag the dangerous configurations, then screen what those servers do when they run.

## What this means for the proxy thesis

Every one of these reports concludes the same thing: the vulnerability is in the layer around the model, not inside it. The model is the most hardened part of the stack. Everything around it, the servers, the configs, the credentials, the tool dispatch, is where the attacks land.

That's the argument for screening at the proxy layer. You can't fix 19,000 repositories. You can't patch every developer's .env habit. You can't inventory every laptop by hand. But you can put a policy layer in front of the MCP server that screens every tool call, blocks the injection patterns, and flags the exfiltration attempts regardless of how the server got there: exposed, misconfigured, or shadow-installed from a zip file.

The infrastructure is the attack surface. Screen the infrastructure.

That screening layer is what we built the RelayShield MCP Proxy Firewall to be. It sits in front of MCP servers and screens tool calls against live threat intelligence before they execute, so how a server was installed stops being the thing your security depends on.

---

Sources: TrendAI 1H 2026 State of AI Security report; OX Security "Welcome to the Jungle" report; ClawSecure AI Agent Threat Report (Sept 2026); JFrog shadow AI detection for developer workstations. All reporting dates October 2026.
