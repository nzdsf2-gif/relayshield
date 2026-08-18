# Arjen's ISP — CALEA / Router Migration Strategy

Started 2026-07-25. Tracking doc for a new relationship — Arjen operates an ISP serving
low-income housing projects in Cleveland, OH.

## Business snapshot

- **Customer base**: ~12,000 subscribers
- **Service**: $18/month, includes an Ethernet private line
- **Market**: low-income housing developments, Cleveland
- **Current router platform**: MikroTik (RouterOS)
- **Under consideration**: migrating to NetElastic routers

## Open question: why migrate off MikroTik?

Not yet established in this doc — need to ask Arjen directly what's driving the
NetElastic evaluation (cost, support, feature gap, reliability, CALEA compliance
specifically, or something else). Worth confirming before treating CALEA as the primary
driver — it may just be one factor among several.

## CALEA / Lawful Intercept — research so far (2026-07-25, WebSearch-sourced, not yet verified against vendor docs)

### Regulatory baseline
- CALEA (Communications Assistance for Law Enforcement Act) requires facilities-based
  broadband/VoIP providers to build in intercept capability for law enforcement, subject
  to a court order/subpoena.
- Two governing technical standards:
  - **J-STD-025** (TIA) — the original CALEA technical standard for circuit-switched
    and packet-mode intercept.
  - **PacketCable Electronic Surveillance Specification (PKT-SP-ESP)** — cable/broadband-
    specific intercept spec.
  - ETSI ES 201 671 is the European-market equivalent (relevant if evaluating vendors
    that lead with ETSI rather than CALEA-specific certification).

### Architecture pattern (consistent across vendors)
Lawful intercept deployments generally split into:
1. **Access function** — lives on the network element (router/switch/BNG) that actually
   sees the target subscriber's traffic. Intercepts and duplicates it.
2. **Mediation device** — sits between the access function and law enforcement, translates
   the raw intercepted traffic into the standard handover format, manages provisioning
   (which subscriber, which court order, when to start/stop), and manages the secure
   delivery channel.
3. **Handover interface** — delivers the mediated, formatted data to the law enforcement
   agency (LEA) collection facility, typically over a dedicated/private connection.

### MikroTik's own CALEA support
- RouterOS has a `calea` package that captures and forwards traffic in real time to an
  external destination (a mediation device or analyzer), as raw `.pcap` or a live network
  stream.
- MikroTik itself is **only the access function** — it does not include a
  standards-compliant mediation/handover layer. A small ISP running MikroTik still needs
  a separate mediation device (in-house build, or a vendor like SS8/Verint/Subsentio) to
  actually be CALEA-compliant end-to-end.
- Real-world reputation note (found in search results, worth being aware of, not
  necessarily relevant to Arjen specifically): MikroTik's CALEA package has been
  reported as a low-cost, widely-deployed option small/regional ISPs use precisely
  because it's cheap — this may be *why* it was originally chosen, and worth understanding
  if NetElastic is being positioned as a more complete/compliant alternative or just a
  different access-layer vendor that still needs the same external mediation piece.

### SS8 (mediation vendor)
- **Xcipio** — real-time mediation platform (the actual intercept/handover mediation
  device).
- **Intellego XT** — the law-enforcement-side query/analytics platform (not something
  an ISP runs; LEAs use this against the delivered data).
- Claims native support for ETSI, 3GPP, and CALEA handovers plus "national variants."
- Runs its own interoperability certification program (Acceler8 Alliance) — testing
  specific network-element/mediation-device combinations for certified compatibility.
- **Gap**: SS8's public site doesn't publish granular protocol/interface specs — real
  evaluation requires talking to their sales/engineering team directly.

### Verint (mediation vendor)
- **STAR-GATE** — mediation platform, explicitly CALEA J-STD-025 and ETSI ES-201-671
  compliant, for both circuit-switched and packet/IP networks.
- Has an ISP-specific product variant for broadband lawful intercept.
- Can connect to multiple network elements simultaneously and deliver to multiple LEA
  destinations at once (relevant for an ISP potentially serving multiple jurisdictions).
- Older/legacy-leaning vendor (some sourced material is dated) — worth checking whether
  Verint's current broadband/ISP-tier offering is still actively sold/supported at
  small-ISP scale, or whether it's now positioned mostly at large carriers.

### Subsentio (found during research, not asked about but relevant)
- Positions itself as a **trusted third-party CALEA compliance service** specifically
  aimed at smaller providers who don't want to build/run intercept infrastructure
  in-house at all — worth a look as an alternative framing to "buy a mediation platform
  and run it yourself." May be a more realistic fit for a 12K-subscriber ISP than SS8/
  Verint's typically carrier-scale platforms.

## Proposed minimum feature set to evaluate NetElastic (and any mediation vendor) against

Not finalized — draft starting point based on the research above:

1. **Access-function intercept capability** on the router itself — real-time duplication
   of a targeted subscriber's traffic (by IP/MAC/subscriber-ID) without alerting the
   subscriber, without degrading their service, and without affecting other subscribers.
2. **Standards-compliant output** — must produce (or feed a mediation device that
   produces) output conforming to J-STD-025 / PacketCable ESP, not a proprietary format
   law enforcement can't ingest.
3. **Provisioning/authorization workflow** — a way to start/stop an intercept tied to a
   specific court order, with an audit trail (who authorized it, when it started/stopped,
   which subscriber) — this is as much a compliance/liability concern as a technical one.
4. **Secure handover delivery** — encrypted, access-controlled delivery to the LEA
   collection point (private line or VPN, not open internet).
5. **Scale headroom** — needs to handle 12K subscribers' worth of routing/traffic without
   the intercept function itself becoming a performance bottleneck.
6. **Support/compliance liability** — who is contractually responsible if an intercept
   fails, is discovered, or is delivered late/wrong under a subpoena — the vendor, or
   Arjen's own ISP? Worth getting in writing regardless of which vendor is chosen.

## Where RelayShield fits — incremental role (per prior guidance, restored 2026-07-28)

**Correction 2026-07-28**: an earlier pass at this section (now removed) speculatively pitched four
generic ISP-security integration points Arjen never asked about (IOC-feed blocking, infected-CPE
detection, a white-label consumer product, NOC enrichment) — a real deviation from prior direction on
this account, caught and reverted. Restoring the actual established framing instead.

**The ISP's actual ask was for an inexpensive solution for LEAs** — not a full CALEA lawful-intercept
build (that stays SS8/Verint/Subsentio's lane, per the vendor research above). The fit is a
**correlated audit log**: a record of IP address + port + timestamp + subscriber-id, indexed for fast
lookup, so that when law enforcement sends a subpoena/court order asking "who had this IP:port at this
time," the ISP can answer quickly. This is the same underlying pattern RelayShield already runs at
scale for breach-record correlation (email → breach exposure, domain → IOC hits) — same shape of
problem (large volume of timestamped records, indexed for fast point lookups), just a different key
(subscriber-id / IP:port instead of email/domain) and a different consumer (the ISP's own compliance
process instead of an end user).

This is deliberately **not** full packet-level intercept — it's session/NAT-style metadata logging
(effectively CGNAT log retention), which is both cheaper to build and closer to what a 12K-subscriber
ISP serving low-income housing can realistically operate, versus a carrier-scale mediation platform.

**Two-source architecture, confirmed 2026-07-28**: the router (MikroTik or NetElastic, whichever Arjen
lands on) generates the CGNAT logs — the IP:port:timestamp side of the correlation. FreeRADIUS generates
the subscriber accounting records — the subscriber-id side, tying a session to a specific customer.
RelayShield's role is to **parse and merge records from both sources into one fast-searchable index**,
so an LEA lookup ("who had this public IP:port at this time") resolves through the CGNAT log to a
session, then through the FreeRADIUS accounting record to the actual subscriber — a join RelayShield
performs and indexes, not something either source does on its own today.

## Gaps RelayShield would need to build

- **No existing schema for this correlation.** RelayShield's current tables key on email/domain/IOC
  value, not subscriber-id + IP:port + timestamp — this would be a new table and a new ingestion path,
  not a reuse of the existing breach/IOC pipeline's data model (just its *pattern*).
- **No CGNAT log ingestion.** Nothing exists yet to pull NAT translation records off MikroTik or
  NetElastic — format differs per platform, unconfirmed which one Arjen lands on, so the parser can't
  be finalized until that decision is made.
- **No FreeRADIUS accounting-record ingestion.** Nothing exists yet to pull subscriber accounting
  records (the subscriber-id side of the join) out of FreeRADIUS — need to confirm which accounting
  attributes Arjen's FreeRADIUS setup actually logs (session start/stop, framed IP, calling-station-id,
  etc.) before scoping the parser.
- **No join/merge logic.** The two sources need to be correlated on session + timestamp to produce one
  answer to "who had this IP:port at this time" — this is the actual new engineering, not just two
  separate ingestion pipelines.
- **No lookup API or LEA-facing workflow.** Needs a way to query the merged index, plus whatever audit
  trail (who requested, under what order, when) the ISP needs for its own liability protection — the
  same provisioning/authorization concern already noted in the minimum-feature-set section above.
- **Retention period undecided.** How long does this data need to be kept to be useful for a real LEA
  request window — not yet discussed with Arjen.

## Open items / next steps

- [ ] Ask Arjen directly what's driving the MikroTik → NetElastic evaluation
- [ ] Get NetElastic's actual CALEA/lawful-intercept documentation (not covered in public
      search results — likely needs direct vendor contact)
- [ ] Decide whether Arjen wants a self-run mediation platform (SS8/Verint-style) or a
      trusted-third-party compliance service (Subsentio-style) — very different cost/
      complexity tradeoff for a 12K-subscriber ISP
- [ ] Confirm current CALEA subpoena/intercept volume Arjen's ISP actually handles (or
      expects to) — shapes whether this is a real operational need or a compliance-
      readiness exercise
- [ ] Confirm the exact prior specification for the correlated audit log (retention period, router-side
      export vs. hosted lookup service, log-write trigger) — not fully recovered from memory, need
      founder confirmation before scoping the build
- [ ] Scope the new subscriber-id/IP:port/timestamp schema and ingestion path once that's confirmed
