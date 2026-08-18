# Draft reply to Jake Lemoine, Stripe

**Status: DRAFT, not sent.** Three answers are yours alone (marked). Every number below was pulled
live from the Stripe API on 2026-08-17, not from memory.

## Verified account facts

| Measure | Value |
|---|---|
| Charges, lifetime | **8**, all paid |
| Gross, lifetime | **$115.92** |
| Refunded | **5 of 8** |
| **Net retained** | **$44.97** |
| Date range | April 2026 to July 2026 |
| Active subscriptions | 2 ($10.99/mo and $24.99/mo list) |
| Last successful payment | 2026-07-18 |
| Account | `acct_1TGqqsL2dcjOeFiY`, `business_type: individual` |
| `card_payments` / `link_payments` | active |
| `crypto_payments` | **inactive** (this is the blocker) |

**Answer honestly.** Jake can see all of this. A projection that does not match a $115.92 history
reads worse than a small number with a clear reason.

---

## Draft

> Hi Jake, thanks for coming back to me. Answers below, and I have kept them precise rather than
> flattering, since you can see the account anyway.
>
> **1. Fund flow.** Two rails to the same metered API. RelayShield sells threat-intelligence and
> identity-exposure checks priced per call, from $0.10 to $0.50, plus monthly bundles. Human
> developers pay by card, which works today. The rail I am missing is the other buyer: autonomous AI
> agents that hold a stablecoin balance and no card. I want an agent to pay per call in USDC and to
> settle to fiat in my Stripe balance alongside the card revenue, so both buyer types land in one
> ledger rather than two. That is what drew me to the Machine Payments Protocol.
>
> Today the crypto side runs outside Stripe on x402 through third-party facilitators. It works
> technically and has produced almost no revenue, which is the honest reason I want a rail with
> Stripe's distribution behind it rather than another crypto-native one.
>
> **2. Products.** A security API with 31 metered endpoints. The main ones check whether an email,
> phone, domain or crypto wallet appears in criminal breach corpora, infostealer logs, or the
> criminal Telegram channels we monitor directly, plus SIM-swap risk and phishing-domain lookalikes.
> Delivery is REST, MCP for AI agents, and STIX/TAXII for SIEMs. It is listed on AWS Marketplace,
> Zapier, n8n and as a MetaMask Snap. Buyers are developers, MSPs and increasingly AI agent
> frameworks.
>
> **3. Current fiat.** Yes, on Stripe today, and the volume is very small: **$115.92 gross across 8
> charges** between April and July 2026, **$44.97 net of refunds**, plus two active monthly
> subscriptions. I am pre-revenue in any meaningful sense and not going to dress that up.
>
> **4. First-year projection.** [FOUNDER: your number. Ground it in something defensible, for
> example the AWS Marketplace listing pipeline or a bundle price times a realistic customer count.
> Do not put a large number here that the $115.92 history cannot support.]
>
> **5. Go-live.** [FOUNDER: your date.]
>
> **6. Funding.** [FOUNDER: bootstrapped / self-funded, or the real figure.]
>
> One thing that would help me most: the dashboard shows Stablecoins and Crypto as **Ineligible**
> with no request button, and the API confirms `crypto_payments` is `inactive`. Support told me the
> capability is not available for my account yet and did not share criteria. If the gate is
> processing volume or account maturity, I would rather know that plainly so I can come back when I
> clear it, instead of guessing.
>
> Thanks,
> Andrew

---

## Notes before sending

- **Do not convert the account from `individual` to company as a way to unblock this.** It triggers
  re-verification on a live revenue account and probably changes nothing. The entity mismatch to
  RelayShield LLC is real and worth fixing on its own merits, separately.
- The closing question is the highest-value part of the email. A named gate is actionable; a polite
  no is not.
- Q4 is the one that can hurt. An inflated projection against a visible $115.92 history damages
  credibility with the exact person deciding whether to escalate.
