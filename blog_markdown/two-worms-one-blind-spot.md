---
title: "Two Worms, One Blind Spot"
slug: two-worms-one-blind-spot
date: 2026-10-23
---

# Two Worms, One Blind Spot

Twice this year, npm has been hit by worms that spread from maintainer machine to maintainer machine. The two campaigns used opposite tricks, and both worked for the same reason: the defenses were watching identities, and the worms were not.

ChainDrop kept the name and stole the identity. MALFEX keeps the payload and rotates the name. Signatures and blocklists are built to catch neither.

## ChainDrop: the signature was real, the signer was not

Attackers hijacked the GitHub account behind the keyv library and shipped poisoned npm releases. The releases carried valid provenance, signed by GitHub Actions. Once installed, the payload raided machines for cloud and registry tokens, then used them to spread to other maintainers. Four hundred packages. Two billion installs.

Provenance tells you who signed a package. It does not tell you whether the signer should be trusted right now. When a maintainer account is hijacked, every release after it carries a valid signature from a compromised source. The cryptography works exactly as designed. The trust assumption underneath it is what breaks.

## MALFEX: the name changes, the loader does not

The MALFEX campaign runs the opposite play. Every two days, give or take, the package name rotates. New name, same payload. Each new package gets a fresh hash and a reputation score of zero, and name-based blocklists fall behind by design.

The infrastructure underneath never changes. The loader is still hosted on GitHub as encrypted shellcode. It still injects into dllhost.exe. It still follows the same nine-line structure. Rebuilding hosting and rewriting the loader costs the operator real time, so they keep the machinery and rotate the wrapper.

## Fingerprint the machinery, not the identity

Both worms tell the same story from opposite ends. Names can be rotated and accounts can be stolen, so neither is a stable thing to detect on. The machinery is stable: what the payload steals, how it spreads, the structure of the loader that carries it.

That is the principle behind structural fingerprinting. Instead of asking whether this package name or this signer has been seen before, ask whether this loader has. RelayShield's scam-kit fingerprinting derives a deterministic identifier from the indicator set, not the filename, so a MALFEX variant matches its family no matter what it calls itself this week.

## Two places to stop a worm

**Before the commit.** Both campaigns move through stolen tokens, and tokens move through commits. A pre-commit hook that scans for credentials stops the spread at the one point the worm cannot route around. RSSCAN is our free, local pre-commit hook: 49 credential patterns (AWS keys, GitHub PATs, Stripe secrets, private keys, LLM provider keys), no account, no API key, no network call, and the source never leaves the machine. A CI check only sees a secret after the push, when it is already in history and has to be rotated.

**At install time.** For everyone downstream, the question is whether this version, from this maintainer, today, shows up in threat intelligence: versions published from hijacked accounts, sudden maintainer changes, typosquat variants, loader structures that match a known family. A package reputation check answers that against the corpus. The signature cannot.

## The takeaway

Signatures prove origin. Names prove nothing at all. Neither proves the source is trustworthy today, and a worm only needs that gap once to start spreading.

Track the machinery. It is the one part the operator cannot afford to change.

---

*RelayShield tracks MALFEX and related loader campaigns in its threat intelligence corpus. RSSCAN is free and open source at github.com/relayshield/rsscan. For API-based supply-chain screening, see api.relayshield.net/developers.*

Tags: npm, supply-chain, malware, threat-intelligence, rsscan
