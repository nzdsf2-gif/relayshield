# Email to Brother / Nephew — Polymarket / RelayShield Pitch

**To:** [Brother / Nephew name]
**Subject:** Quick read — the Polymarket hack and something I built that would have caught it

---

Hey [Name],

Saw you're connected to the prediction markets space and wanted to share something quick — I think the timing is relevant.

I wrote a breakdown of the Polymarket attack from last month. The short version: Lazarus Group (North Korean state hackers, responsible for over $3 billion stolen from crypto since 2016) didn't break Polymarket's smart contracts. They stole credentials. Specifically, oracle signing keys that were sitting in criminal stealer log archives for days before the attacker used them.

The reason I'm sending this to you: the exact signals that preceded that attack — employee credentials showing up in infostealer archives, service account API keys exposed, domain identity risk spiking — are exactly what my platform monitors in real time.

I built RelayShield (relayshield.net) — an identity security API that watches the credential layer: breach exposure, infostealer activity, stolen session cookies, service account key exposure. It's the kind of signal monitoring that would have flagged the Polymarket precursors days before the attacker used them.

The blog post I wrote walks through the attack chain step by step and maps five specific detection signals to the timeline. It's a quick read:

[link — paste your Hashnode URL here]

The reason this matters for prediction markets specifically: the attack surface isn't the smart contracts. It's the credential layer — oracle keys, admin accounts, developer credentials. That's exactly what RelayShield monitors.

The economics are straightforward. Polymarket lost an estimated $8–14 million. The detection layer I'm describing costs $499/month. That's $6,000 a year — roughly 0.06% of the low-end loss estimate.

If there's anyone in your network at a prediction markets company who's thinking about security posture after this incident, I'd love a 20-minute intro call. I can demo everything live — real data, five active threat intelligence capabilities, no slides.

No pressure at all — if the timing is off or the fit isn't there, totally fine. Just thought of you given what you're working on.

Talk soon,
Andrew

---
RelayShield | relayshield.net | +1 (339) 203-9730
