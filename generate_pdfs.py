"""Generate branded PDFs for RelayShield solution briefs."""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

# Brand colors
NAVY   = colors.HexColor('#0F1F3D')
TEAL   = colors.HexColor('#00B5A5')
LIGHT  = colors.HexColor('#F4F6FA')
GRAY   = colors.HexColor('#6B7280')
WHITE  = colors.white
BLACK  = colors.HexColor('#1A1A2E')

def make_styles():
    base = getSampleStyleSheet()

    styles = {
        'h1': ParagraphStyle('h1',
            fontName='Helvetica-Bold', fontSize=22, textColor=NAVY,
            spaceAfter=4, spaceBefore=0, leading=26),
        'tagline': ParagraphStyle('tagline',
            fontName='Helvetica', fontSize=11, textColor=TEAL,
            spaceAfter=16, spaceBefore=2, leading=15),
        'h2': ParagraphStyle('h2',
            fontName='Helvetica-Bold', fontSize=13, textColor=NAVY,
            spaceAfter=6, spaceBefore=14, leading=17,
            borderPad=0),
        'body': ParagraphStyle('body',
            fontName='Helvetica', fontSize=10, textColor=BLACK,
            spaceAfter=5, spaceBefore=2, leading=14, alignment=TA_JUSTIFY),
        'bullet': ParagraphStyle('bullet',
            fontName='Helvetica', fontSize=10, textColor=BLACK,
            spaceAfter=3, spaceBefore=1, leading=14,
            leftIndent=14, firstLineIndent=0),
        'quote': ParagraphStyle('quote',
            fontName='Helvetica-Oblique', fontSize=11, textColor=NAVY,
            spaceAfter=8, spaceBefore=8, leading=16,
            leftIndent=20, rightIndent=20,
            borderColor=TEAL, borderWidth=3, borderPad=10,
            backColor=LIGHT),
        'footer': ParagraphStyle('footer',
            fontName='Helvetica', fontSize=8, textColor=GRAY,
            spaceAfter=0, spaceBefore=0, leading=11, alignment=TA_CENTER),
        'contact_name': ParagraphStyle('contact_name',
            fontName='Helvetica-Bold', fontSize=11, textColor=NAVY,
            spaceAfter=3, spaceBefore=2, leading=14),
        'contact': ParagraphStyle('contact',
            fontName='Helvetica', fontSize=10, textColor=GRAY,
            spaceAfter=2, spaceBefore=0, leading=13),
        'small': ParagraphStyle('small',
            fontName='Helvetica', fontSize=8, textColor=GRAY,
            spaceAfter=4, spaceBefore=2, leading=11),
    }
    return styles


def header_band(canvas, doc, title, subtitle):
    """Draw the top header band on every first page."""
    w, h = letter
    canvas.saveState()
    # Navy header rectangle
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 1.15*inch, w, 1.15*inch, fill=1, stroke=0)
    # Teal accent stripe
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 1.15*inch, 0.18*inch, 1.15*inch, fill=1, stroke=0)
    # Title text
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 18)
    canvas.drawString(0.38*inch, h - 0.52*inch, title)
    canvas.setFont('Helvetica', 10)
    canvas.setFillColor(colors.HexColor('#A0B4CC'))
    canvas.drawString(0.38*inch, h - 0.78*inch, subtitle)
    # Footer line
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.2)
    canvas.line(0.5*inch, 0.55*inch, w - 0.5*inch, 0.55*inch)
    canvas.setFillColor(GRAY)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawCentredString(w/2, 0.38*inch, 'relayshield.net  ·  relayshieldadmin@gmail.com  ·  RelayShield LLC, Andover MA')
    canvas.restoreState()


def page_header_footer(canvas, doc, subtitle):
    """Subsequent pages: thin header + footer."""
    w, h = letter
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 0.38*inch, w, 0.38*inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 0.38*inch, 0.1*inch, 0.38*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(0.28*inch, h - 0.24*inch, 'RelayShield')
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#A0B4CC'))
    canvas.drawRightString(w - 0.4*inch, h - 0.24*inch, subtitle)
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1)
    canvas.line(0.5*inch, 0.52*inch, w - 0.5*inch, 0.52*inch)
    canvas.setFillColor(GRAY)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawCentredString(w/2, 0.35*inch, f'relayshield.net  ·  Page {doc.page}')
    canvas.restoreState()


def table_style(header_bg=NAVY, alt_bg=LIGHT):
    return TableStyle([
        ('BACKGROUND', (0,0), (-1,0), header_bg),
        ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 7),
        ('TOPPADDING', (0,0), (-1,0), 7),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, alt_bg]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#D1D9E6')),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])


def md_inline(text, style):
    """Convert basic markdown bold/italic to reportlab XML.
    Preserves existing <b>, <i> tags; only escapes bare & characters."""
    import re
    text = text.replace('&', '&amp;')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    return Paragraph(text, style)


# ─── MSP BRIEF ────────────────────────────────────────────────────────────────

def build_msp(output_path):
    s = make_styles()
    w, h = letter
    margins = dict(leftMargin=0.6*inch, rightMargin=0.6*inch,
                   topMargin=1.35*inch, bottomMargin=0.75*inch)

    HDR_TITLE    = 'MSP Partner Brief'
    HDR_SUBTITLE = 'The proactive identity protection layer your SMB clients can\'t get anywhere else'

    def first_page(canvas, doc):
        header_band(canvas, doc, HDR_TITLE, HDR_SUBTITLE)
    def later_pages(canvas, doc):
        page_header_footer(canvas, doc, 'MSP Partner Brief')

    doc = SimpleDocTemplate(output_path, pagesize=letter, **margins)
    story = []

    # ── Gap section ──
    story.append(Paragraph('The Gap in Every MSP Stack', s['h2']))
    story.append(md_inline(
        'Your clients are protected against malware, ransomware, and network intrusion. '
        'What their stack almost certainly does not cover is **identity** — the attack surface that precedes every one of those threats.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'Identity-based attacks don\'t announce themselves. They begin weeks before damage occurs: '
        'a credential appearing in a breach database, a SIM swap quietly redirecting a phone number, '
        'an infostealer log listing an employee\'s saved passwords on a criminal marketplace. '
        'By the time your endpoint or SIEM fires an alert, the attacker has already been inside — '
        'authenticated, legitimate, and invisible.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '**Identity protection has become a client checkbook requirement.** '
        'Cyber insurance carriers now ask about breach monitoring at renewal. '
        'State data protection regulations increasingly require documented credential monitoring programs. '
        'Clients who have experienced an incident are actively asking their MSP what identity monitoring they provide. '
        'Most MSP stacks have no answer. RelayShield is that answer.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Differentiation ──
    story.append(Paragraph('What Makes RelayShield Different: We Work While the Attack Is Forming', s['h2']))
    story.append(md_inline(
        'Every other identity protection service on the market operates on the same model: '
        'detect that an account has already been taken over, then notify the victim. '
        '**RelayShield\'s architecture is fundamentally different.** '
        'We analyze attack signals while attacks are still forming — and intervene before financial loss occurs.',
        s['body']))
    story.append(Spacer(1, 6))

    cell_style = ParagraphStyle('cell', fontName='Helvetica', fontSize=9,
        textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0)
    hdr_style = ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=9,
        textColor=WHITE, leading=13, spaceAfter=0, spaceBefore=0)

    vs_data = [
        [Paragraph('What competitors do', hdr_style), Paragraph('What RelayShield does', hdr_style)],
        [Paragraph('"Your account has been taken over.\nHere\'s what happened."', cell_style),
         Paragraph('"An attack is forming against your account.\nHere\'s what to do right now to stop it."', cell_style)],
    ]
    t_vs = Table(vs_data, colWidths=[3.5*inch, 3.5*inch])
    t_vs.setStyle(table_style(header_bg=TEAL))
    story.append(KeepTogether([t_vs, Spacer(1, 8)]))

    # ── Multi-vector correlation ──
    story.append(Paragraph('Multi-Vector Signal Correlation', s['h2']))
    story.append(md_inline(
        'RelayShield monitors five attack surfaces simultaneously and correlates events across all of them. '
        'When two or more signals fire within a correlation window, RelayShield escalates to a '
        '**Coordinated Attack Warning** — the only commercial product at this price point that does this.',
        s['body']))
    story.append(Spacer(1, 6))

    def _p(text, bold=False):
        """Paragraph with wrapping for table cells."""
        sty = ParagraphStyle('tc', fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=9, textColor=WHITE if bold else BLACK, leading=13,
            spaceAfter=0, spaceBefore=0, wordWrap='CJK')
        return Paragraph(text, sty)

    signal_data = [
        [_p('Signal', bold=True), _p('What We Detect', bold=True), _p('When We Fire', bold=True)],
        [_p('Credential breach'), _p('Employee email in a breach database'),
         _p('Within hours — before attackers begin credential stuffing')],
        [_p('Infostealer log exposure'), _p('Device credentials in criminal Telegram markets'),
         _p('24–72 hrs ahead of HIBP — before attackers replay stolen sessions')],
        [_p('SIM swap'), _p('Phone number hijacked at carrier level'),
         _p('Real-time carrier query — before 2FA bypass completes')],
        [_p('Domain lookalike'), _p('Typosquat domains impersonating your client'),
         _p('Within hours of registration — before phishing campaigns launch')],
        [_p('OAuth supply chain'), _p('Rogue app accessing Microsoft 365 or Google Workspace'),
         _p('On detection — with one-tap revocation instructions')],
    ]
    t_sig = Table(signal_data, colWidths=[1.4*inch, 2.5*inch, 3.1*inch])
    t_sig_style = table_style()
    t_sig_style.add('BACKGROUND', (0, 0), (-1, 0), NAVY)
    t_sig.setStyle(t_sig_style)
    story.append(KeepTogether([t_sig, Spacer(1, 8)]))

    story.append(md_inline('**Eleven predictive attack chains recognized — identity and crypto asset surfaces:**', s['body']))
    for item in [
        'Breach + SIM swap → predicted account takeover',
        'Infostealer + VPN credential exposure → predicted ransomware precursor',
        'Smishing + SIM swap → predicted financial account drain',
        'Domain lookalike + breach → predicted spear phishing campaign',
        'OAuth app breach + SIM swap → all downstream connected services at risk',
        'OAuth app breach + credential harvesting → active OAuth token exploitation',
        'SIM swap + flagged wallet counterparty → CRITICAL crypto exchange drain in progress',
        'Credential breach + flagged wallet counterparty → coordinated identity and asset attack',
        'Port-out fraud + flagged wallet counterparty → CRITICAL dual-vector crypto theft chain',
    ]:
        story.append(md_inline('• ' + item, s['bullet']))
    story.append(Spacer(1, 4))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Infostealer ──
    story.append(Paragraph('Infostealer Malware — The Fastest-Growing Enterprise Threat', s['h2']))
    story.append(md_inline(
        'Infostealer malware infected **11.1 million devices in 2025**, putting 3.3 billion credentials into criminal markets. '
        'Entry-level toolkits are available via Malware-as-a-Service for $60/month. In a single pass, '
        'they harvest every saved browser password, active session cookie, VPN credential, and cloud platform login '
        'from an infected device — packaged and sold in criminal Telegram channels within 24–72 hours.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'Stolen VPN and remote access credentials are the primary entry point for ransomware deployment. '
        'The infostealer is the reconnaissance. The ransomware is the conclusion.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'RelayShield monitors criminal Telegram channels and infostealer log markets in near real-time. '
        'When an employee\'s credentials appear in a log, the alert fires within hours — '
        'with a four-step device remediation protocol — before session replay or ransomware deployment begins.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        'No other MSP-accessible product monitors the Telegram channels where these logs are sold.',
        s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── SIM swap carrier surface ──
    story.append(Paragraph('SIM Swap — The Only Cost-Effective Carrier Surface Monitor', s['h2']))
    story.append(md_inline(
        'SIM swap fraud bypasses 2FA entirely. An attacker who controls a phone number receives every '
        'verification code, banking alert, and account recovery text sent to that number. '
        'Once complete, they own every account secured with that number.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'RelayShield is the **only cost-effective solution that monitors the carrier surface for SIM swap activity** '
        'at SMB-accessible pricing. We query the carrier in real time via Twilio Lookup v2 — '
        'detecting active port or SIM swap events and alerting the user immediately, before account access completes. '
        'Enterprise SIM swap monitoring solutions start at $10K+/year. RelayShield delivers equivalent '
        'carrier-level detection at a fraction of the cost.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Alert delivery ──
    story.append(Paragraph('Alert Delivery: Where Your Clients Already Are', s['h2']))
    story.append(md_inline(
        'RelayShield delivers every alert via **WhatsApp and Telegram** — no app to install, '
        'no dashboard to check, no training required. For MSP-managed business accounts, alerts go simultaneously '
        'to the affected employee and the admin — your point of contact sees every incident the moment it fires.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Partner tiers ──
    story.append(Paragraph('Partner Tiers', s['h2']))
    def _pt(text, bold=False):
        sty = ParagraphStyle('tc2', fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=9, textColor=WHITE if bold else BLACK, leading=13,
            spaceAfter=0, spaceBefore=0, wordWrap='CJK')
        return Paragraph(text, sty)

    tier_data = [
        [_pt('Plan', bold=True), _pt('Best For', bold=True), _pt('Price/Mo', bold=True), _pt('MSP Margin', bold=True)],
        [_pt('Business Starter'), _pt('Mobile-first sole proprietors — single-owner businesses, freelancers'), _pt('$19.99/acct'), _pt('20%')],
        [_pt('Business Starter + Domain'), _pt('Sole proprietors with a business website — adds typosquat domain monitoring'), _pt('$24.99/acct'), _pt('20%')],
        [_pt('Business Basic'), _pt('Small teams up to 5 seats — breach, SIM swap, infostealer + admin dashboard'), _pt('$89.99/acct'), _pt('25%')],
        [_pt('Business Shield'), _pt('Growing SMBs up to 10 seats — all Basic + per-seat SIM + priority alerts'), _pt('$139.99/acct'), _pt('25%')],
        [_pt('Business Shield Pro'), _pt('Established SMBs up to 25 seats — full stack + compliance reporting'), _pt('$299.99/acct'), _pt('25%')],
        [_pt('Crypto Shield'), _pt('Crypto-native businesses, DeFi operators, Web3 companies'), _pt('$19.99/seat'), _pt('20%')],
    ]
    t2 = Table(tier_data, colWidths=[1.5*inch, 3.1*inch, 1.1*inch, 0.9*inch])
    t2.setStyle(table_style())
    story.append(KeepTogether([t2, Spacer(1, 4)]))
    story.append(md_inline(
        '**On Crypto Shield for MSPs:** For client bases that include crypto-native businesses — '
        'exchanges, DeFi operators, Web3 agencies — Crypto Shield adds wallet monitoring, '
        'counterparty risk screening, and address poisoning detection. Relevant for financial services or technology verticals.',
        s['small']))
    story.append(Paragraph(
        'White-label arrangement available for partners with 10+ seats. Volume pricing at 50+ seats.',
        s['small']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── API section ──
    story.append(Paragraph('For Security-Forward MSP Partners: API Access', s['h2']))
    story.append(md_inline(
        'RelayShield exposes its full monitoring capability via REST API — enabling MSPs and MSSPs to embed '
        'RelayShield intelligence directly into their own tooling, SIEM integrations, and SOAR playbooks.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline('**Transactional API endpoints (PAYG and subscription):**', s['body']))
    for ep in [
        'POST /v1/breach — credential breach lookup ($0.10/call)',
        'POST /v1/sim-swap — real-time carrier SIM swap check ($0.25/call)',
        'POST /v1/domain — domain lookalike scan ($0.30/call)',
        'POST /v1/infostealer — infostealer log exposure check ($0.50/call)',
        'POST /v1/oauth-watchlist — OAuth &amp; token exposure: breach watchlist + live stealer log corpus ($0.30/call)',
        'POST /v1/crypto-intel — wallet address risk, token honeypot & tax flags, counterparty screening ($0.30/call)',
        'GET /v1/intel/cve — actively-exploited vulnerability lookup, cross-referenced against CISA KEV ransomware activity',
    ]:
        story.append(md_inline('• ' + ep, s['bullet']))
    story.append(Spacer(1, 4))

    # ── Crypto asset intelligence (after API endpoints) ──
    story.append(md_inline('**Crypto Asset Intelligence — Cross-Surface Attack Detection:**', s['body']))
    story.append(md_inline(
        'The /v1/crypto-intel endpoint goes beyond a simple lookup. When it flags a wallet counterparty '
        'as high risk, RelayShield records that signal in the same 72-hour correlation window as identity '
        'signals. If a SIM swap, credential breach, or port-out fraud event has also fired for the same '
        'user within that window, RelayShield escalates to a composite CRITICAL alert.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'A SIM swap alert and a flagged wallet transaction arriving within 72 hours is the most common '
        'crypto exchange drain pattern. **No competitor has both signal streams and the correlation layer '
        'to connect them.** Callable via REST API, MCP tool, or through the Telegram and WhatsApp bots '
        'for Crypto Shield subscribers.',
        s['body']))
    story.append(Spacer(1, 4))

    story.append(md_inline('**Threat Intelligence API — live:**', s['body']))
    story.append(md_inline(
        'MSSPs operating at scale can query RelayShield\'s live IOC database via <b>GET /v1/intel/telegram</b>. '
        'The feed aggregates <b>200,000+ indicators</b> from two source categories — '
        '<b>8 verified criminal Telegram channels</b> (infostealer log markets, credential dumps, SIM swap service listings — '
        'the underground sources that surface threats 24–72 hours before public breach databases); and '
        '<b>11 authoritative threat intelligence feeds</b>: '
        '<b>ThreatFox (abuse.ch)</b> — malware IOCs tagged by family (LummaC2, RedLine, Vidar, Stealc, Raccoon, and 14 others); '
        '<b>URLhaus (abuse.ch)</b> — malicious URLs for active malware distribution; '
        '<b>Feodo Tracker aggressive (abuse.ch)</b> — ~8,000 active botnet C2 IPs (Emotet, QakBot, Dridex, IcedID, TrickBot); '
        '<b>MalwareBazaar (abuse.ch)</b> — malware SHA256 hashes tagged by family; '
        '<b>Spamhaus DROP/EDROP</b> — IP ranges operated by cybercrime networks; '
        '<b>AbuseIPDB</b> — crowdsourced IP abuse reports (confidence ≥90%); '
        '<b>Emerging Threats</b> — compromised IP blocklist, updated daily; and '
        '<b>AlienVault OTX</b> — community threat pulses covering domains, IPs, and file hashes. '
        'Pass any domain, IP, URL, or SHA256 hash to check for known malware infrastructure association — '
        'ahead of reputation services that lag by days or weeks. IOC data retained 90 days.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '<b>Price-to-performance:</b> Enterprise threat intelligence platforms start at '
        '$30K–$300K/year for equivalent IOC coverage. RelayShield delivers <b>200,000+ queryable indicators '
        'at $499/month</b> — the same enrichment data your clients\' enterprise competitors pay $5K+/month to access.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '<b>Global ransomware CVE intelligence:</b> RelayShield also ingests the full CISA Known Exploited '
        'Vulnerabilities (KEV) catalog daily — 1,600+ actively-exploited CVEs tracked, with vulnerabilities '
        'tied to known ransomware campaigns flagged separately. When a vendor/product your clients run appears '
        'with an actively-exploited, ransomware-linked CVE, you have a concrete, dated reason to open a '
        'remediation conversation — not a generic "patch your systems" reminder.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '**Developer subscription — live today:** $499/mo for 10,000 API calls, $999/mo unlimited. '
        'Self-serve signup at relayshield.net/developers — covers all metered endpoints above plus the '
        'threat intelligence feed. Built for security engineers at small-to-mid-size companies building '
        'internal SIEM/SOAR tooling, and security SaaS vendors embedding breach and infostealer data into '
        'their own product. No commitment, cancel anytime.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '**Mid-market MSSP feed (coming):** A bulk export tier ($1,500–$3,000/mo) for MSSPs running '
        'this data through their own SIEM/SOAR pipeline at scale across many client tenants, delivered as '
        'a continuous feed rather than per-query lookups. Contact us to join early access.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Why easy to sell ──
    story.append(Paragraph('Why This Is Easy to Sell', s['h2']))
    def _pe(text, bold=False):
        sty = ParagraphStyle('tc3', fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=9, textColor=WHITE if bold else BLACK, leading=13,
            spaceAfter=0, spaceBefore=0, wordWrap='CJK')
        return Paragraph(text, sty)

    easy_data = [
        [_pe('Factor', bold=True), _pe('Detail', bold=True)],
        [_pe('Fills a genuine gap'), _pe("Identity monitoring is a client ask MSPs currently can't answer")],
        [_pe('Compliance driver'), _pe('Cyber insurance carriers and state regulations require documented credential monitoring')],
        [_pe('Zero friction'), _pe('WhatsApp/Telegram delivery — clients onboard in under 5 minutes, no MSP involvement after referral')],
        [_pe('Instant credibility'), _pe('First alert proves value immediately — clients see a real breach or risk on day one')],
        [_pe('Recurring MRR'), _pe('Monthly per-account subscription — predictable, stackable revenue')],
        [_pe('Natural upsell'), _pe('Pairs with any existing endpoint, backup, or antivirus contract — not a replacement')],
        [_pe('Carrier-level differentiation'), _pe('SIM swap monitoring at carrier depth — no competitor offers this at SMB pricing')],
    ]
    t3 = Table(easy_data, colWidths=[1.8*inch, 5.2*inch])
    t3.setStyle(table_style())
    story.append(KeepTogether([t3, Spacer(1, 8)]))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Pitch ──
    story.append(Paragraph('The MSP Pitch', s['h2']))
    story.append(Paragraph(
        '"Your clients\' identity stack has a blind spot: the carrier surface, the criminal Telegram channels, '
        'and the attack signals that fire weeks before a breach becomes visible. '
        'RelayShield closes that gap — monitoring every credential, phone number, domain, and infostealer log '
        'in real time, correlating signals across the full attack surface, and alerting your clients '
        'while the attack is still forming. Not after the damage is done."', s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Day one ──
    story.append(Paragraph('What Your Clients Get on Day One', s['h2']))
    for i, item in enumerate([
        'Immediate breach check on all monitored email addresses',
        'Infostealer log scan — credentials checked against criminal market exposure',
        'SIM swap monitoring activated on all registered phone numbers',
        'Domain lookalike scan across 500M+ registered domains',
        'OAuth &amp; token exposure audit — breach watchlist + live stealer log corpus; rogue app detection active',
        'Predictive attack chain engine active — correlation monitoring begins immediately across 11 chains',
        'Cross-surface correlation live — identity signals correlated against crypto wallet risk signals for clients with digital asset exposure',
        'Step-by-step remediation guidance built into every alert',
    ], 1):
        story.append(md_inline(f'<b>{i}.</b>  {item}', s['bullet']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Getting started ──
    story.append(Paragraph('Getting Started', s['h2']))
    for label, body in [
        ('Pilot program:', 'Free 30-day Business Starter + Domain account for the MSP principal — full feature access for a single seat. No team seats, no commitment required.'),
        ('Onboarding:', 'Clients self-onboard via a 2-minute WhatsApp or Telegram flow. No MSP involvement required after the initial referral.'),
        ('Support:', 'Direct line to RelayShield founder for all partner questions.'),
    ]:
        story.append(md_inline(f'<b>{label}</b> {body}', s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=6))

    # ── Contact ──
    story.append(Paragraph('Contact', s['h2']))
    story.append(Paragraph('Andrew Gibbs — Founder, RelayShield', s['contact_name']))
    story.append(Paragraph('relayshieldadmin@gmail.com  ·  relayshield.net', s['contact']))
    story.append(Paragraph('Andover, MA  ·  RelayShield LLC (Est. April 2026)', s['contact']))
    story.append(Paragraph('25 years in telecommunications security. Built on a carrier-layer detection foundation no competitor has replicated.', s['contact']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'RelayShield is a registered business in the Commonwealth of Massachusetts (ID: 001963633).',
        s['small']))

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f'✅  {output_path}')


# ─── EXECUTIVE BRIEFING ───────────────────────────────────────────────────────

def build_exec(output_path):
    s = make_styles()
    w, h = letter
    margins = dict(leftMargin=0.6*inch, rightMargin=0.6*inch,
                   topMargin=1.35*inch, bottomMargin=0.75*inch)

    HDR_TITLE    = 'Executive Briefing'
    HDR_SUBTITLE = 'Talking Points — Identity Attack Protection'

    def first_page(canvas, doc):
        header_band(canvas, doc, HDR_TITLE, HDR_SUBTITLE)
    def later_pages(canvas, doc):
        page_header_footer(canvas, doc, 'Executive Briefing')

    doc = SimpleDocTemplate(output_path, pagesize=letter, **margins)
    story = []

    # Mission
    story.append(Paragraph('Mission Statement', s['h2']))
    story.append(Paragraph(
        'RelayShield detects identity attacks the moment they start and delivers '
        'plain-English guidance to stop them — before the damage is done.',
        s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # SIM Swap urgency
    story.append(Paragraph('Are SIM Swaps Really That Urgent?', s['h2']))
    story.append(md_inline(
        'Most people think of cybersecurity as antivirus and firewalls — software protecting a device. '
        'SIM swap is different. It attacks your <i>identity</i>, not your device, and it bypasses every piece of software security you have.',
        s['body']))
    story.append(Spacer(1, 6))

    sim_data = [
        ['Malware / Virus', 'SIM Swap'],
        ['Attacks your device', 'Attacks your phone number — the master key to every account'],
        ['Requires you to click something', 'Happens at the carrier — you do nothing wrong'],
        ['Antivirus can catch it', 'No software on earth detects it — your carrier just reroutes your number'],
        ['Takes time to spread', 'Account takeover completes in under 10 minutes'],
        ['Affects one device', 'Unlocks your bank, email, crypto, business accounts simultaneously'],
    ]
    t = Table(sim_data, colWidths=[2.8*inch, 4.2*inch])
    t.setStyle(table_style(header_bg=TEAL))
    story.append(KeepTogether([t, Spacer(1, 6)]))
    story.append(Paragraph(
        '"A virus gets into your computer. A SIM swap gets into your life."', s['quote']))

    story.append(md_inline(
        'The attacker calls your carrier, impersonates you, and within minutes your phone goes dead and every '
        'two-factor authentication code — for your bank, your email, your business systems — goes to them. '
        'By the time you realise what happened, your accounts are drained and your passwords are changed.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # Six attack types
    story.append(Paragraph('What Does RelayShield Actually Protect Against?', s['h2']))
    story.append(md_inline('Six attack types, all live today:', s['body']))
    for item in [
        '**SIM Swap & Port-Out Fraud** — We detect the moment your number is hijacked at the carrier level and fire an alert before the attacker reaches your accounts',
        '**Data Breach Exposure** — Your email and credentials appear in a breach. We tell you within hours: what was exposed, how serious it is, what to change first',
        '**Phishing & Lookalike Domains** — Someone registers yourcompany-support.com to scam your customers. You hear about it the same day',
        '**OTP Interception / Smishing** — Fake "your bank needs verification" texts designed to steal one-time codes. We detect the pattern and warn you',
        '**OAuth Token Theft** — Third-party apps connected to your Google, Microsoft, or Slack accounts get breached. We flag which tokens are now compromised',
        '**Coordinated Multi-Vector Attacks** — A breach today followed by a SIM swap attempt 48 hours later isn\'t coincidence — it\'s a planned attack chain. We connect those dots',
    ]:
        story.append(md_inline('• ' + item, s['bullet']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # Exposure
    story.append(Paragraph("Where You're Exposed and Don't Know It", s['h2']))
    story.append(md_inline("Most executives are surprised by these:", s['body']))
    for item in [
        "**Your phone number IS your password.** Every 'forgot my password' flow, every bank login, every 2FA code goes to your number. One carrier call from an attacker and they own everything",
        '**Breached passwords you\'re still using.** 13 billion credentials are in circulation right now. Yours are probably in there. Most people never find out until the account is already taken',
        '**Fake versions of your company website.** Attackers register near-identical domains to target your customers or staff. You\'d never know unless someone is watching',
        "**Apps still connected to your accounts.** Every 'Sign in with Google' you've ever clicked left a token. Old apps get breached. That token still works",
        '**Employee offboarding gaps.** A departing employee who still has OAuth access to company tools is a live attack surface. Most businesses have dozens of these open right now',
    ]:
        story.append(md_inline('• ' + item, s['bullet']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # Differentiation
    story.append(Paragraph('How Is RelayShield Different?', s['h2']))

    cell_style = ParagraphStyle('cell', fontName='Helvetica', fontSize=9,
        textColor=BLACK, leading=13, spaceAfter=0, spaceBefore=0)
    hdr_style = ParagraphStyle('hdr', fontName='Helvetica-Bold', fontSize=9,
        textColor=WHITE, leading=13, spaceAfter=0, spaceBefore=0)

    diff_data = [
        [Paragraph('The Competition', hdr_style), Paragraph('RelayShield', hdr_style)],
        [Paragraph('Alerts you after an account is taken over', cell_style),
         Paragraph('Alerts you while the attack is forming — before it completes', cell_style)],
        [Paragraph('Requires an app download or portal login', cell_style),
         Paragraph('Lives in WhatsApp or Telegram — where your people already are', cell_style)],
        [Paragraph('Reports incidents', cell_style),
         Paragraph('Tells you exactly what to do in the next 10 minutes, in plain English', cell_style)],
        [Paragraph('Monitors one threat type', cell_style),
         Paragraph('Correlates breach + SIM swap + phishing as a single coordinated attack', cell_style)],
        [Paragraph('Watches your device', cell_style),
         Paragraph('Watches your identity — the layer carriers and apps don\'t protect', cell_style)],
        [Paragraph('Built by software engineers', cell_style),
         Paragraph('Built on 25 years of carrier-layer expertise — we understand the telco attack surface from the inside', cell_style)],
    ]
    t2 = Table(diff_data, colWidths=[2.8*inch, 4.2*inch])
    t2.setStyle(table_style())
    story.append(KeepTogether([t2, Spacer(1, 8)]))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # Experience
    story.append(Paragraph('What Does the Experience Actually Look Like?', s['h2']))
    story.append(md_inline('No app. No dashboard. No training required.', s['body']))
    story.append(md_inline(
        'A customer signs up in under 2 minutes via WhatsApp or Telegram. From that point:', s['body']))
    story.append(md_inline('• <b>Normal days:</b> Silence. No noise.', s['bullet']))
    story.append(md_inline('• <b>When something is detected:</b> A plain-English message arrives. Example:', s['bullet']))
    story.append(Paragraph(
        '⚠️ SIM Swap Alert — Your number showed a carrier change event 4 minutes ago. '
        'If you didn\'t request this, call AT&T Fraud at 877-844-5584 immediately and say '
        '"I need to report a SIM swap." Lock your SIM PIN at att.com/simprotection. '
        'Your bank accounts and email passwords should be changed now.',
        s['quote']))
    story.append(md_inline(
        '• <b>The customer acts within minutes</b>, not days. Most competitive products send a weekly digest email that gets ignored.',
        s['bullet']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # One-liners
    story.append(Paragraph('Audience-Specific One-Liners', s['h2']))
    for audience, line in [
        ('Telcos:', '"You currently get the complaint call after the hijack. We get you the prevention call before it. That\'s the difference between a fraud claim and a loyalty moment."'),
        ('Enterprise IT Teams:', '"You can patch every server in your environment. You cannot patch an employee\'s phone number. We cover the gap you can\'t."'),
        ('SMB Business Owners:', '"Your bank account, your email, your point-of-sale system — all one phone call to your carrier away from being stolen. We\'re the alarm that fires the moment that call happens."'),
        ('MSPs / MSSPs:', '"Identity monitoring is the line item your clients expect on every proposal and the one most stacks don\'t have. We\'re API-first, multi-tenant, and structured for resale. You can be live this week."'),
    ]:
        story.append(md_inline(f'<b>{audience}</b>', s['body']))
        story.append(Paragraph(line, s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # Objection handlers
    story.append(Paragraph('Universal Objection Handlers', s['h2']))
    for obj, resp in [
        ('"We already have antivirus / EDR / a SIEM."',
         '"Those protect your devices and network. We protect your identity — the layer that bypasses all of those controls when it\'s compromised."'),
        ('"Is this just a breach monitoring service?"',
         '"Breach monitoring tells you what already happened. We correlate what\'s happening now — breach exposure followed by a SIM swap attempt is an active attack in progress. We flag it mid-chain."'),
        ('"Our employees are trained on phishing."',
         '"Training helps. It doesn\'t stop your carrier from being socially engineered by an attacker who already bought your employee\'s credentials from a breach database."'),
        ('"We\'re too small to be a target."',
         '"The attacks are automated. You\'re not targeted because of who you are — you\'re targeted because your credentials are in a database. Every business with a phone number qualifies."'),
        ('"What does it cost?"',
         '"Personal protection starts at $14.99/month. Business from $19.99. Less than one fraudulent transaction, one hour of IT recovery time, or one wire transfer reversal attempt."'),
    ]:
        story.append(md_inline(f'<b>{obj}</b>', s['body']))
        story.append(Paragraph(resp, s['quote']))

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f'✅  {output_path}')


if __name__ == '__main__':
    base = '/Users/andrewgibbs/Side SaaS Hustle'
    build_msp(f'{base}/RelayShield_MSP_Solution_Brief.pdf')
    build_exec(f'{base}/RelayShield_Executive_Briefing.pdf')
