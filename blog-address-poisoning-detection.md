> **STATUS: Draft — ready to post**

# The Scam That Hides in Plain Sight: How Address Poisoning Empties Wallets — and How to Catch It

A 2025 academic study measured 270 million address-poisoning attacks across Ethereum and BNB Smart Chain over two years. 17 million victims. At least $83.8 million in confirmed losses.

You've probably never heard of address poisoning. That's by design.

---

## How It Works

Every crypto wallet displays a transaction history. When you send funds, the destination address appears in that list. The next time you send to the same address, most users do what feels natural: copy it from history.

Address poisoning exploits exactly that habit.

An attacker creates a wallet address that matches the first 4–6 characters and last 4–6 characters of an address you've transacted with before. They then send you a tiny "dust" transaction — sometimes fractions of a cent — from their lookalike address. It appears in your transaction history, sitting right next to the real address.

Both addresses start with `0x1A2B` and end with `C3D4`. One is yours. One is the attacker's. The 32 characters in the middle are completely different — but they're the 32 characters nobody checks.

The next time you go to send funds, you copy from history. If you copy the wrong one, your funds go to the attacker. The transaction confirms. It's irreversible.

---

## The Timing Trap Nobody Talks About

Here's the detail that makes this attack more dangerous than it first appears — and it came from real on-chain forensics published by Bitget Research this month.

Attackers don't wait for you to transact and then respond. They monitor the mempool — the queue of pending, unconfirmed transactions — in real time.

When your transaction enters the mempool, attackers can see it before it confirms. They immediately inject their poisoning transaction, sometimes with higher gas, so it can land on-chain *before your transaction finalizes*. The result: the fake address appears earlier in your wallet history than your real transaction.

A user in the documented case did everything right. They sent a small test transaction first. They confirmed it worked. Then they sent $1.6 million to the same address.

But the poisoning transaction targeting their wallet was recorded on-chain almost two minutes before the test transaction appeared. When the user looked at their history to copy the address for the large transfer, the fake appeared first.

In this case, the user didn't fall for it — they verified the full address. Most users don't.

---

## Why Standard Advice Doesn't Fully Protect You

The standard guidance is: always check the full address before sending. That's correct. But there are two failure modes that make it harder than it sounds.

**Failure mode 1: The test transaction illusion.** Users are told to send a small test amount first. This feels like due diligence. But if a poisoning transaction lands in your history before your test transaction, and you copy "the address you just tested" from history — you may be copying the fake one. The test worked because you originally copied the correct address. The second copy is where the error happens.

**Failure mode 2: History reordering.** Some wallets sort by recency, some by block order, some by the user's last scroll position. When a poisoning transaction is deliberately timed to appear near a real transaction, the ordering you see depends on your wallet's display logic — not the actual sequence. What looks like "the address I just used" may not be.

---

## The Scale of the Problem

Chainalysis estimated $17 billion was stolen through crypto scams and fraud in 2025. Address poisoning sits inside that number — and it's growing because it targets behavior, not software.

You can audit a smart contract. You can verify a seed phrase. You cannot easily train away the habit of copying a familiar-looking address from a list of familiar-looking addresses.

The attack works on experienced users. It works on users who use hardware wallets. It works on users who know what a SIM swap is and have already protected themselves. Because none of those defenses guard against copying the wrong address from your own wallet history.

---

## What We Built

We shipped address poisoning detection in Crypto Shield this week.

Here's how it works:

Every time a Crypto Shield subscriber sends a transaction, the destination address is recorded as a known-good address in their profile. On every inbound transaction, we run a similarity check — comparing the sender's address against every address that subscriber has ever sent funds to.

We score prefix match and suffix match independently. If an inbound sender matches 4 or more characters at the start *and* 4 or more characters at the end of any known-good address, it's flagged. If either dimension hits 6 characters, or if the transaction value is dust, the confidence level goes to HIGH.

When a match is found, we send an immediate Telegram alert:

> **☠️ ADDRESS POISONING ATTEMPT DETECTED**
>
> **Confidence:** HIGH ⛔
> **Match:** 6 prefix chars + 6 suffix chars
>
> **Real address (yours):** `0x1A2B34...C5D6E7`
> **Fake sender (lookalike):** `0x1A2B91...C5D6E7`
>
> ⚠️ Do NOT copy this address from your transaction history.
>
> **What to do right now:**
> • Do not send any funds until you have verified the full destination address from its original source — not from your wallet history
> • If you have a pending transaction queued, cancel it before confirming
> • Cross-reference the full 42-character address against the original source (exchange withdrawal page, verified contact, or QR code you scanned directly)
> • If you already sent funds to the wrong address, act immediately: document the transaction hash, report to your exchange, and file with the FBI IC3 at ic3.gov — recovery is rare but the window is short

The side-by-side comparison is deliberate. The point isn't just to tell you something suspicious happened — it's to show you exactly what the real and fake addresses look like next to each other, so you can see the difference the attacker is counting on you to miss.

The detection runs on every inbound transaction, on every chain we monitor: Ethereum, Base, Polygon, Arbitrum, and Optimism.

---

## What You Should Do

**1. Never copy addresses from transaction history.** Copy from the original source — the exchange withdrawal screen, the contact you verified out-of-band, the QR code from a trusted interface. History is where poisoning transactions are designed to land.

**2. Verify the full address, not just the ends.** If you must use history, check every character. Yes, all 42. This is the only reliable manual defense.

**3. Use a contact book with verified addresses.** Most wallet software has this. An attacker cannot modify a saved contact. An attacker can inject a transaction that looks like a saved contact, which is why verifying the contact at save-time matters.

**4. Enable automated detection.** Manual checks fail under time pressure, distraction, and habitual behavior. Automated detection doesn't.

---

## The Broader Pattern

The most dangerous crypto attacks in 2025 and 2026 are not exploiting smart contract bugs. They're exploiting interface design, user behavior, and the cognitive shortcuts that make software usable.

Address poisoning works because wallet history is a trusted surface. SIM swapping works because SMS looks like authentication. Phishing works because branded email looks legitimate.

The attack surface isn't the blockchain. It's the distance between what users see and what's actually happening. Security that operates at that layer — monitoring behavior signals in real time, flagging anomalies before confirmation — is what the next generation of crypto security looks like.

---

*Crypto Shield monitors your wallets across Bitcoin, Ethereum, Base, Polygon, Arbitrum, Optimism, Solana, and TON — and now detects address poisoning attempts in real time. Monitoring also covers SIM swap detection, infostealer exposure, token risk, and DeFi liquidation warnings. All alerts delivered via Telegram.*

*[Start monitoring → crypto.relayshield.net]*
