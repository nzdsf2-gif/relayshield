# Reply to revettr_x402, CDP Discord Show-and-Tell thread

They asked whether `wallet-risk` returns a freshness field today, or whether the verdict is point in
time with the TTL left to the caller. It was the second, and worse: no timestamp at all. Shipped the
fix before replying so this reads as "here it is" rather than "good idea".

---

## The reply

Straight answer: it did not. Worse, we were not returning `checked_at` either, so you could not have
recorded when the observation happened without stamping it yourself.

Your framing is right. At five cents against a six cent average, the integration is a cache keyed on
payTo whether we design for that or not, and if we do not state a lifetime the caller picks one
optimistically.

Shipped today on `wallet-risk`:

```json
"observed_at": "2026-08-08T00:22:31Z",
"valid_for_seconds": 3600,
"expires_at": "2026-08-08T01:22:31Z",
"degraded": false
```

The TTL is asymmetric, which is the opposite of what a naive cache does:

- flagged 24h, a hit stays a hit
- clean 1h, your point exactly, it is the verdict that flips without announcing itself
- degraded 5m, an upstream was unavailable so we say so rather than return a confident LOW

That last one closed a real trap. An outage used to return `risk_level: LOW` with an empty flag
list, indistinguishable from a genuine clean result, so you could cache "safe" off our downtime.

`wallet-screen-batch` carries the same four fields per result, not one TTL for the call.

Live now, schema in `api.relayshield.net/openapi.json`.

One gap: those numbers are a judgement, not a measurement. I have no data on how long a clean
verdict actually holds. If anyone here has measured flip times across a real address population, I
would rather use that than my guess.

---

## Notes before posting

- Post from `.Cryptonomicon`, the handle that owns the thread.
- Do not re-link the blog post, it is already up-thread.
- The closing question is the second reason for them to reply, and only someone who has run this at
  scale can answer it.
- If pricing comes up: `wallet-risk` is still $0.05. The freshness contract is not a paid upgrade,
  and saying so stops it reading as monetising their idea.
