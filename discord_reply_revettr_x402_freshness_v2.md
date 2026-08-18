# Discord reply to revettr_x402, CDP server, freshness thread

Draft 2026-08-08, for the founder to post. Second reply in the thread that produced the freshness
contract. Register matches his: lowercase, dense, no marketing.

Dash rule observed: no em-dashes, en-dashes or double hyphens.

---

took the degraded point and went looking for other places we do the same thing, on the assumption
that if we got it wrong once we got it wrong more than once. found two, both live, both billing.

the domain lookalike scan runs candidates through a bounded dns sweep and threw away whatever did not
finish inside the timeout. a truncated sweep reported fewer lookalikes, sometimes zero, and looked
identical to a domain that genuinely has none. it also reported candidates_checked as the number
generated rather than the number actually resolved, so coverage read highest exactly when it was
worst.

the crypto intel endpoint catches an upstream failure, logs it, and carries on with an empty flag
list. that produced risk LOW plus an advisory reading "no risk signals detected on this address",
off an outage.

both now set degraded and drop to the short ttl, and the advisory is replaced rather than left
standing.

on the ttls themselves, your censored data point landed. i did not want to publish a number that
sounds measured when it is not, so they ship as policy defaults, the docs say that, and they say
valid_for_seconds is a caching hint rather than a safety guarantee, because the real bound is
upstream detection latency and we do not control it.

the age dependent clean ttl i did not build, and not because i disagree. we hold no first seen signal
for an address or an email anywhere in the service. the one age shaped field we already fetch is the
registration age of a lookalike we found, which is the age of the wrong object. so honouring it means
an extra upstream call on every request, which is latency and cost on a five cent endpoint. that is a
pricing decision rather than a code change, so it is written up and parked rather than quietly
dropped.

the underlying point, that a flat constant is wrong at both ends of the distribution, i agree with. i
just do not want to fake the input to it.
