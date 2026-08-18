# Hashnode support appeal — AutoMod archiving of Elastic Security integration guide

**Blog:** relayshield.hashnode.dev (RelayShield Security Intelligence)
**Post:** "Ingesting RelayShield Threat Intelligence into Elastic Security"
**Slug:** elastic-security-threat-intelligence-integration
**Filed:** 2026-07-29

---

Subject: AutoMod is archiving our own product documentation — request for human review

Hello,

AutoMod has archived the same post three times on our blog, relayshield.hashnode.dev, and I would
like a human to review the decision.

The post is "Ingesting RelayShield Threat Intelligence into Elastic Security." All three copies are
currently visible in our Archived tab, each tagged AutoMod, corresponding to publish attempts on
2026-07-28 and 2026-07-29. In each case the post published normally, remained live for roughly an
hour, and was then archived with no notification. We received no email, no in-app notice, and no
stated reason, so it took us most of a working day to discover that AutoMod was the cause rather
than a platform bug.

For context on what the post is: RelayShield is a commercial threat intelligence service. The post
is first-party integration documentation for our own API, explaining how a customer configures
Elastic Security's built-in Threat Intel TAXII 2.x and MISP integrations to consume our feed. It is
the same genre of content as any vendor's "how to connect our product to your SIEM" guide.

I can only guess at what triggered the classifier, but the two likeliest candidates are:

1. **`curl` examples containing an API key header.** The post shows requests of the form
   `curl -s https://api.relayshield.net/v1/intel/taxii/ -H "X-RS-API-KEY: YOUR_API_KEY"`. The value
   is the literal placeholder `YOUR_API_KEY` — no real credential appears anywhere in the post.
2. **Subject matter language.** The post describes indicators sourced from criminal marketplaces
   where stolen credentials are traded. This is descriptive security writing about a defensive
   product, not instructions for wrongdoing.

Requests:

- Please restore the post, or confirm it cannot be restored so we can stop retrying.
- Please tell us which element triggered AutoMod, so we can avoid it rather than guess.
- More broadly: **can API documentation containing placeholder credential headers be published on
  Hashnode at all?** If the answer is no, that is a reasonable policy and we will host our technical
  documentation elsewhere — but we need to know before writing more of it. We have fourteen other
  security posts live on this blog and no prior moderation issues.

We have deliberately stopped republishing after the third archive, since repeatedly reposting
flagged content seems likely to escalate against the account, which is not our intent.

Thank you,
RelayShield
support@relayshield.net
