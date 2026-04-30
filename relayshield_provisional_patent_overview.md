# RelayShield — Provisional Patent Overview
**Prepared for Attorney Review and Filing**
*Draft: April 2026 | Inventor: Andrew Gibbs | Entity: RelayShield LLC (Massachusetts)*

---

## TITLE OF INVENTION

**System and Method for Ordered Breach Remediation with Attack Chain Correlation and Conversational Identity Protection Delivery**

---

## FIELD OF THE INVENTION

This invention relates to cybersecurity systems and methods, and more specifically to automated identity breach detection, multi-signal attack chain correlation, ordered remediation sequencing, and interactive delivery of actionable security guidance through conversational messaging platforms.

---

## BACKGROUND

### The Problem With Existing Identity Protection Products

Existing identity protection products — including credit monitoring services, dark web alert services, and password managers — share three structural deficiencies that leave users exposed after a breach is detected:

**1. Detection without sequencing.** Existing products notify users that a breach occurred but provide no ordered remediation path. Users are told to "change your password" without guidance that this action alone is insufficient and may be actively counterproductive if performed before revoking active authenticated sessions.

**2. Session token blindness.** The cybersecurity industry has broadly under-addressed the session token attack vector. A stolen session token grants an attacker full authenticated access to an account — no password, no 2FA required. Standard guidance to "change your password" does not revoke existing sessions. An attacker holding a stolen session token retains access indefinitely even after a password change. No existing consumer identity protection product specifically detects session token exposure in breach data and instructs users to revoke sessions *before* resetting passwords.

**3. Single-signal detection.** Existing products detect individual events (a breach, a SIM swap, a suspicious message) in isolation. No existing product correlates signals across attack vectors in real time to detect and respond to a coordinated multi-stage identity attack in progress.

**4. Passive delivery.** Existing products deliver alerts via email, app notification, or web dashboard — channels that are themselves commonly compromised in the breach event being reported, and channels that require the user to initiate a separate interaction to receive remediation guidance.

---

## SUMMARY OF THE INVENTION

The present invention provides a system and method for automated identity breach remediation comprising:

1. **An ordered remediation sequence engine** that enforces a specific, clinically-derived order of protective actions following breach detection — specifically requiring session revocation to precede password reset when session token exposure is detected — and delivers each step as an interactive conversational prompt via a messaging platform.

2. **An attack chain correlation engine** that maps exposed data classes from breach intelligence sources to predicted downstream attack vectors, assigns composite severity scores based on data class combinations, and escalates alert severity and remediation content based on correlation across multiple concurrent signals.

3. **A coordinated attack detection engine** that maintains a temporal event window per monitored identity and identifies when multiple independent threat signals (breach detection, SIM swap event, suspicious SMS submission, OTP interception warning) co-occur within a defined time window, escalating to a composite coordinated attack alert with cross-signal remediation guidance.

4. **A conversational remediation interface** delivered through a widely-deployed consumer messaging platform (specifically WhatsApp or equivalent), enabling interactive step-by-step completion of remediation actions, confirmatory response handling, and follow-up engagement — all within the messaging interface without requiring installation of a dedicated application.

5. **A tiered remediation content engine** that varies the depth, specificity, and escalation path of remediation guidance based on the subscriber's service tier, the specific data classes exposed, and the detected attack vectors.

---

## DETAILED DESCRIPTION OF THE INVENTION

### Component 1 — Ordered Breach Remediation Sequence

The core method of the invention establishes that the order of protective actions following a breach is as clinically significant as the actions themselves. The invention enforces the following sequence:

**Step 1: Session Revocation (when session token exposure detected)**
When breach data includes session token or authentication cookie exposure, the system identifies this condition via data class matching against a predefined high-value data class registry and instructs the user to revoke all active authenticated sessions across identity providers (Google, Microsoft, social media platforms) *before* taking any other action. The instruction specifically states that password reset performed before session revocation does not terminate active attacker sessions.

**Step 2: Email Forwarding Rule Audit**
The user is directed to audit email forwarding rules — the primary mechanism by which attackers establish persistent inbox access that survives both password resets and session revocations. The system provides platform-specific navigation paths for Gmail and Microsoft Outlook.

**Step 3: Recovery Contact Verification**
The user is directed to verify that account recovery email addresses and phone numbers have not been modified by an attacker to establish persistent re-entry capability.

**Step 4: Connected Application Audit**
The user is directed to audit OAuth-connected third-party applications and revoke access granted to unrecognised applications. The system additionally cross-references the breached service against a maintained watchlist of high-risk OAuth-capable SaaS applications that frequently hold delegated access tokens.

**Step 5: Active Device Session Audit**
The user is directed to review all active device sessions and sign out of unrecognised devices, with platform-specific navigation paths for each major identity provider.

**Step 6: Password Reset (final step)**
Password reset is presented as the final step in the sequence, following session revocation and backdoor closure. The system explicitly communicates that password reset performed without the preceding steps does not close attacker access and may create false confidence.

**Step 7: Follow-up Confirmation**
The system sends a follow-up message within a defined interval requesting confirmation that the ordered steps have been completed, and offers additional remediation guidance for steps the user indicates were not completed.

This specific ordered sequence — and in particular the inversion of the conventional "change your password first" guidance by placing session revocation first and password reset last — constitutes a novel remediation method not present in any existing identity protection product or published guidance.

---

### Component 2 — Attack Chain Correlation Engine

The system maintains a registry of breach data classes (drawn from breach intelligence API responses) and maps each data class to one or more predicted downstream attack vectors. The mapping includes but is not limited to:

| Exposed Data Class | Predicted Attack Vector |
|---|---|
| Phone numbers | Smishing campaign targeting; SIM swap social engineering |
| Passwords | Credential stuffing; account takeover via replay attack |
| Session cookies / auth tokens | Session hijacking; AiTM (Adversary-in-the-Middle) replay |
| SSN / passport / driver's licence | Voice-based vishing impersonation; synthetic identity fraud |
| Physical addresses | Package interception; physical social engineering |
| Date of birth + name | Knowledge-based authentication bypass |
| Financial account numbers | Account takeover; fraudulent wire transfer initiation |
| API keys / OAuth tokens | Supply chain pivot; lateral movement into connected systems |
| Healthcare data | Insurance fraud; Medicare impersonation |

**Composite Severity Scoring:** The system assigns an initial severity label (CRITICAL / HIGH / MEDIUM / LOW) based on the breach source category, then applies upward adjustments based on data class combinations:

- Any password exposure: severity increases one level (floor: HIGH)
- Session token or auth cookie exposure: severity is CRITICAL regardless of source; session revocation step injected into remediation sequence
- Identity document exposure (SSN, passport, driver's licence): severity is CRITICAL regardless of source; vishing escalation block injected
- Password manager service breach with password exposure: severity is HIGH minimum regardless of source
- SaaS/OAuth-capable application breach: OAuth supply chain escalation block injected, listing specific revocation steps for the breached service

**Predictive Attack Path Generation:** Based on the data class combination, the system generates a ranked list of likely follow-on attack methods and incorporates corresponding warnings into the alert delivery. A phone number exposure combined with a carrier name in the breach source generates a SIM swap risk warning. A password exposure from a corporate email provider generates a Business Email Compromise (BEC) warning for business-tier subscribers.

---

### Component 3 — Coordinated Attack Detection Engine

The system maintains a per-user event window — a time-bounded record (default: 48–72 hours) of security signals observed for a monitored identity. Signal types include:

- Breach alert fired for this identity
- Suspicious SMS analysis submitted by the user (forwarded smishing attempt)
- OTP warning command invoked (user received unexpected one-time passcode)
- SIM swap event detected via carrier lookup
- Vishing warning command invoked
- Domain lookalike detected for this user's registered domain

When two or more signals co-occur within the event window, the system evaluates the combination against a correlation matrix:

| Signal Combination | Coordinated Attack Classification |
|---|---|
| SIM swap detected + suspicious SMS submitted (prior 48 hrs) | CRITICAL: Coordinated smishing-to-SIM-swap attack chain |
| Breach alert fired + OTP warning invoked (same session) | HIGH: Credential stuffing with real-time account takeover attempt |
| Domain lookalike detected + breach alert fired | HIGH: Phishing infrastructure deployment coincident with credential exposure |
| Breach alert fired + SIM swap detected (same user, 24 hrs) | CRITICAL: Multi-vector coordinated identity attack |

When a coordinated attack is detected, the system fires a separate composite alert that: (a) identifies the correlated signals, (b) assigns a composite severity level, (c) provides an integrated remediation path addressing all detected vectors simultaneously, and (d) for business-tier subscribers, notifies the account administrator.

---

### Component 4 — Conversational Remediation Interface

The system delivers all breach alerts, remediation guidance, and follow-up interactions through a conversational messaging platform API. The architecture provides:

**Command-Response Interface:** Users interact via short-code text commands (SWEEP, SESSIONS, PHONE, SMS, EMAIL, ATTACH, REUSE, OTP, WASCAM, VERIFY, DOMAIN, STATUS, ADD, REMOVE) that trigger specific remediation workflows. Each command returns a structured response containing step-by-step guidance, platform-specific navigation paths, and calls-to-action for related commands.

**Inbound Message Classification:** The system receives inbound messages via webhook, classifies them as commands, confirmatory responses, or forwarded threat content, and routes to the appropriate handler. Forwarded suspicious SMS messages are extracted from the message body, URL-extracted, and submitted to a URL safety analysis API for real-time verdict.

**Session-Aware Delivery:** The system tracks the 24-hour WhatsApp conversation session window per user and queues alerts that arrive outside the session window, delivering them when the next user-initiated message reopens the session. Pending alerts are stored in the user record and delivered before processing the user's command.

**Tiered Content Delivery:** Alert and remediation content varies by subscription tier. Personal-tier subscribers receive detection alerts with generic remediation steps. Business-tier subscribers receive carrier-specific hardening steps, employee co-notification, OAuth audit guidance, domain monitoring alerts, and admin dashboard commands. Business Shield Pro subscribers additionally receive FCC complaint guidance, eSIM disable procedures, and compliance documentation.

---

### Component 5 — SIM/eSIM Swap and Port-Out Detection

The system periodically queries a carrier intelligence API (specifically Twilio Lookup v2 or equivalent) for each monitored phone number on a defined schedule (every 4 hours). The query returns:

- A boolean indicator of SIM or eSIM change within the prior 24-hour window
- A timestamp of the detected change event
- The current carrier name associated with the number

**SIM/eSIM Swap Detection:** A positive swap indicator triggers an alert delivery to the user's registered messaging address. The alert content is tiered by subscription level, ranging from carrier callback numbers (personal tier) to carrier-specific SIM lock procedures and eSIM profile audit steps (business tiers) to eSIM provisioning restriction and FCC complaint filing (Pro tier).

**Port-Out Fraud Detection:** The system persists the carrier name from each clean check to the user record. When the carrier name changes between check intervals — indicating a number port to a new carrier without user-initiated contact — the system classifies the event as suspected port-out fraud and fires a CRITICAL alert bypassing the standard deduplication window. The port-out alert communicates that all SMS-based two-factor authentication is compromised and provides port-back request procedures.

**Deduplication with Port-Out Bypass:** Standard SIM swap alerts are suppressed if an alert for the same user was delivered within a 23-hour window. Port-out alerts bypass this deduplication and always fire on detection, recognising that port-out fraud is a discrete irreversible event rather than a persistent state.

---

### Component 6 — Domain Threat Intelligence Engine

For business-tier subscribers with registered domains, the system performs daily automated threat checks:

**Lookalike Domain Detection:** The system generates a corpus of typosquat and homoglyph permutations of each monitored domain using character substitution, addition, and transposition methods, then performs parallel DNS resolution for each permutation. Registrations detected trigger an alert with the lookalike domain and recommended protective registration.

**MX Record Change Detection:** The system queries DNS MX records for monitored domains via a public DNS-over-HTTPS API and persists the current MX record set. Changes between check intervals — indicating potential email routing hijack — trigger a CRITICAL alert with investigation guidance.

**Domain Expiry Monitoring:** The system queries domain registration data via the RDAP API for each monitored domain and alerts at 30-day, 14-day, and 7-day thresholds before expiry, preventing domain hijack via expiry-and-reregistration.

---

## CLAIMS (PROVISIONAL — FOR ATTORNEY REFINEMENT)

1. A method for ordered breach remediation comprising: detecting exposure of a monitored identity in a breach intelligence data source; identifying data classes exposed in said breach; when session token or authentication cookie data classes are identified, generating a remediation sequence in which session revocation instructions are delivered to the user prior to password reset instructions; delivering said ordered remediation sequence via a conversational messaging platform API; and requesting confirmation of completion of each remediation step.

2. The method of Claim 1, wherein the remediation sequence further comprises: forwarding rule audit instructions delivered after session revocation and before password reset; recovery contact verification instructions; OAuth-connected application audit instructions; active device session audit instructions; and password reset instructions delivered as the final step in the sequence.

3. A method for attack chain correlation comprising: receiving breach intelligence data including one or more exposed data class identifiers; mapping each exposed data class to one or more predicted downstream attack vectors via a predefined correlation registry; generating a composite severity score based on the combination of mapped attack vectors; and appending attack-vector-specific escalation content to a breach alert message based on the composite severity score.

4. The method of Claim 3, wherein the composite severity score is escalated to a maximum severity level when exposed data classes include any of: session tokens; authentication cookies; social security numbers; passport numbers; or driver's licence numbers.

5. A method for coordinated attack detection comprising: maintaining a time-bounded event window for each monitored user identity; recording, within said event window, two or more independent security signal types from the group consisting of: breach alert detection; SIM swap detection; suspicious SMS submission by the user; unexpected OTP receipt warning; and domain lookalike detection; evaluating recorded signals against a correlation matrix defining known multi-vector attack chains; and when a matching combination is detected, generating a composite coordinated attack alert that addresses all correlated vectors in a unified remediation response.

6. A system for identity breach remediation comprising: a breach detection module configured to query a breach intelligence API on a defined schedule for each monitored email address; an attack chain correlation module configured to map detected breach data classes to downstream attack vectors; an ordered remediation sequencing module configured to generate a step-ordered remediation plan in which session revocation precedes password reset when session token exposure is detected; a conversational delivery module configured to transmit alerts and remediation guidance via a messaging platform API and receive and classify user responses; and a coordinated attack detection module configured to correlate signals from multiple threat detection subsystems within a time-bounded event window.

7. The system of Claim 6, further comprising: a SIM swap detection module configured to query a carrier lookup API on a defined interval, detect SIM or eSIM change events, detect carrier name changes indicative of port-out fraud, and generate tiered alert content based on the subscriber's service tier.

8. The system of Claim 6, further comprising: a domain threat intelligence module configured to generate lookalike domain permutations, perform DNS resolution for each permutation, monitor MX record changes, and monitor domain registration expiry for registered business domains.

---

## ABSTRACT

A system and method for identity breach detection, attack chain correlation, and ordered remediation delivery through a conversational messaging interface. The system detects identity exposure in breach intelligence data, maps exposed data classes to predicted downstream attack vectors using a predefined correlation registry, generates a composite severity score, and delivers an ordered remediation sequence to the affected user. The ordered sequence enforces session revocation before password reset when session token exposure is detected — inverting conventional guidance in recognition that password reset does not terminate active attacker sessions. The system additionally maintains a temporal event window per monitored identity and correlates independent threat signals (breach detection, SIM swap events, suspicious SMS submissions, unexpected OTP receipts) to detect coordinated multi-vector attacks and generate composite remediation responses. All detection, correlation, and remediation guidance is delivered through a conversational messaging platform API, enabling interactive step-completion and follow-up confirmation without requiring installation of a dedicated application.

---

## INVENTOR BACKGROUND

Andrew Gibbs brings 25 years of telecommunications security expertise to this invention, including direct experience with the carrier-layer infrastructure that underlies SIM swap and port-out fraud — attack vectors that no existing consumer identity protection product monitors at the carrier level. The ordered remediation sequence and attack chain correlation methods described herein emerge from applied experience with the gap between breach detection (widely available) and effective breach response (effectively absent from existing products).

---

## NOTES FOR ATTORNEY

- **Filing type recommended:** Provisional utility patent application. Establishes priority date at low cost. Grants 12 months to file full utility application.
- **Primary novel claims:** (1) session revocation before password reset as an ordered method claim; (2) attack chain correlation from breach data classes; (3) coordinated attack detection via temporal signal correlation.
- **Secondary novel claims:** SIM/eSIM swap detection with port-out fraud differentiation; domain threat intelligence combining lookalike detection, MX monitoring, and expiry monitoring in a unified daily scan.
- **Prior art to search:** LifeLock/Norton, Aura, Identity Guard, HIBP, Credit Karma, Experian IdentityWorks — none are known to implement ordered session-first remediation or multi-signal coordinated attack detection.
- **Implementation:** All described components are currently operational in production as AWS Lambda functions (Python) with DynamoDB state persistence. Working implementation strengthens enablement argument.
- **Budget guidance:** $1,500–$3,000 for provisional filing; consult attorney on whether full utility filing is warranted given competitive landscape.
