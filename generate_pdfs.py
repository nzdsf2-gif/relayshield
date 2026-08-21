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
        'What their stack almost certainly does not cover is **identity**: the attack surface that precedes every one of those threats.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'Identity-based attacks don\'t announce themselves. They begin weeks before damage occurs: '
        'a credential appearing in a breach database, a SIM swap quietly redirecting a phone number, '
        'an infostealer log listing an employee\'s saved passwords on a criminal marketplace. '
        'By the time your endpoint or SIEM fires an alert, the attacker has already been inside, '
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
        'We analyze attack signals while attacks are still forming, and intervene before financial loss occurs.',
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
        '**Coordinated Attack Warning**: the only commercial product at this price point that does this.',
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
         _p('Within hours, before attackers begin credential stuffing')],
        [_p('Infostealer log exposure'), _p('Device credentials in criminal Telegram markets'),
         _p('24 to 72 hrs ahead of public breach databases, before attackers replay stolen sessions')],
        [_p('SIM swap'), _p('Phone number hijacked at carrier level'),
         _p('Real-time carrier query, before 2FA bypass completes')],
        [_p('Domain lookalike'), _p('Typosquat domains impersonating your client'),
         _p('Within hours of registration, before phishing campaigns launch')],
        [_p('OAuth supply chain'), _p('Rogue app accessing Microsoft 365 or Google Workspace'),
         _p('On detection, with one-tap revocation instructions')],
    ]
    t_sig = Table(signal_data, colWidths=[1.4*inch, 2.5*inch, 3.1*inch])
    t_sig_style = table_style()
    t_sig_style.add('BACKGROUND', (0, 0), (-1, 0), NAVY)
    t_sig.setStyle(t_sig_style)
    story.append(KeepTogether([t_sig, Spacer(1, 8)]))

    story.append(md_inline('**Eleven predictive attack chains recognized, identity and crypto asset surfaces:**', s['body']))
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
    story.append(Paragraph('Infostealer Malware, The Fastest-Growing Enterprise Threat', s['h2']))
    story.append(md_inline(
        'Infostealer malware infected **11.1 million devices in 2025**, putting 3.3 billion credentials into criminal markets. '
        'Entry-level toolkits are available via Malware-as-a-Service for $60/month. In a single pass, '
        'they harvest every saved browser password, active session cookie, VPN credential, and cloud platform login '
        'from an infected device, packaged and sold in criminal Telegram channels within 24 to 72 hours.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'Stolen VPN and remote access credentials are the primary entry point for ransomware deployment. '
        'The infostealer is the reconnaissance. The ransomware is the conclusion.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'RelayShield monitors criminal Telegram channels and infostealer log markets in near real-time. '
        'When an employee\'s credentials appear in a log, the alert fires within hours, '
        'with a four-step device remediation protocol, before session replay or ransomware deployment begins.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        'No other MSP-accessible product monitors the Telegram channels where these logs are sold.',
        s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── LLMjacking & Shadow AI (added 2026-07-28) ──
    story.append(Paragraph('LLMjacking & Shadow AI, The Credential Class Your Stack Cannot See', s['h2']))
    story.append(md_inline(
        'The same infostealer that harvests browser passwords also harvests AI provider API keys. '
        'That changes the economics of a single leaked credential.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'A stolen password gives an attacker access. A stolen LLM API key gives them **your client\'s '
        'credit card with no spending limit**. Published incidents range from tens of thousands of dollars '
        'per day to a **$500K single-month bill** from one unthrottled key. The underground price for a '
        'stolen LLM key is roughly **$30**: $30 to buy, six figures to absorb.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'The exposure is larger than most MSPs realise, because it is not confined to approved AI tools:',
        s['body']))
    for line in [
        '**Shadow AI**: developers sign up for DeepSeek, Moonshot Kimi and Alibaba Qwen directly, on '
        'personal accounts, outside procurement. None of it appears in an MSP\'s SaaS inventory.',
        '**One key, many models**: a single leaked Hugging Face token bills against DeepSeek, Qwen, Kimi '
        'and NVIDIA models through Inference Providers. The attacker never needs a vendor key.',
        '**Cloud keys are now AI keys**: Amazon Bedrock issues dedicated long-lived API keys used as '
        'bearer tokens. They are not IAM credentials, and tooling built to spot AKIA keys does not see them.',
    ]:
        story.append(md_inline('• ' + line, s['body']))
        story.append(Spacer(1, 2))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '**RelayShield detects exposed API keys across 14 LLM and AI providers** in criminal stealer log '
        'archives, OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Amazon Bedrock, Groq, Replicate, '
        'LangSmith, Hugging Face, NVIDIA NIM, DeepSeek, Moonshot Kimi, Alibaba Qwen, and Alibaba Cloud.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        '**Coverage no other tooling provides.** Gitleaks, the most widely deployed open-source secret '
        'scanner, ships **zero** detection rules for DeepSeek, Moonshot, Qwen or NVIDIA. An MSP relying on '
        'standard secret scanning is blind to all four. RelayShield is not scanning repositories for keys a '
        'client might leak; it is scanning the criminal channels where leaked keys are already being sold.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        'The MSP conversation this opens: "Do you know which AI services your developers are using, and '
        'whether any of those keys are already for sale?"',
        s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── SIM swap carrier surface ──
    story.append(Paragraph('SIM Swap, The Only Cost-Effective Carrier Surface Monitor', s['h2']))
    story.append(md_inline(
        'SIM swap fraud bypasses 2FA entirely. An attacker who controls a phone number receives every '
        'verification code, banking alert, and account recovery text sent to that number. '
        'Once complete, they own every account secured with that number.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'RelayShield is the **only cost-effective solution that monitors the carrier surface for SIM swap activity** '
        'at SMB-accessible pricing. We query the carrier in real time via Twilio Lookup v2, '
        'detecting active port or SIM swap events and alerting the user immediately, before account access completes. '
        'Enterprise SIM swap monitoring solutions start at $10K+/year. RelayShield delivers equivalent '
        'carrier-level detection at a fraction of the cost.',
        s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Alert delivery ──
    story.append(Paragraph('Alert Delivery: Where Your Clients Already Are', s['h2']))
    story.append(md_inline(
        'RelayShield delivers every alert via **WhatsApp and Telegram**: no app to install, '
        'no dashboard to check, no training required. For MSP-managed business accounts, alerts go simultaneously '
        'to the affected employee and the admin, your point of contact sees every incident the moment it fires.',
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
        [_pt('Business Starter'), _pt('Mobile-first sole proprietors, single-owner businesses, freelancers'), _pt('$19.99/acct'), _pt('20%')],
        [_pt('Business Starter + Domain'), _pt('Sole proprietors with a business website, adds typosquat domain monitoring'), _pt('$24.99/acct'), _pt('20%')],
        [_pt('Business Basic'), _pt('Small teams up to 5 seats, breach, SIM swap, infostealer + admin dashboard'), _pt('$89.99/acct'), _pt('25%')],
        [_pt('Business Shield'), _pt('Growing SMBs up to 10 seats, all Basic + per-seat SIM + priority alerts'), _pt('$139.99/acct'), _pt('25%')],
        [_pt('Business Shield Pro'), _pt('Established SMBs up to 25 seats, full stack + compliance reporting'), _pt('$299.99/acct'), _pt('25%')],
        [_pt('Crypto Shield'), _pt('Crypto-native businesses, DeFi operators, Web3 companies'), _pt('$19.99/seat'), _pt('20%')],
        [_pt('Multi-Site Shield'), _pt('Multi-location businesses, franchises, retail chains, distributed teams'), _pt('From $45/loc'), _pt('Reseller pricing')],
    ]
    t2 = Table(tier_data, colWidths=[1.5*inch, 3.1*inch, 1.1*inch, 0.9*inch])
    t2.setStyle(table_style())
    story.append(KeepTogether([t2, Spacer(1, 4)]))
    story.append(md_inline(
        '**On Crypto Shield for MSPs:** For client bases that include crypto-native businesses, '
        'exchanges, DeFi operators, Web3 agencies, Crypto Shield adds wallet monitoring, '
        'counterparty risk screening, and address poisoning detection. Relevant for financial services or technology verticals.',
        s['small']))
    story.append(Paragraph(
        'White-label arrangement available for partners with 10+ seats. Volume pricing at 50+ seats.',
        s['small']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── API section ──
    story.append(Paragraph('For Security-Forward MSP Partners: API Access', s['h2']))
    story.append(md_inline(
        'RelayShield exposes its full monitoring capability via REST API, enabling MSPs and MSSPs to embed '
        'RelayShield intelligence directly into their own tooling, SIEM integrations, and SOAR playbooks.',
        s['body']))
    story.append(Spacer(1, 4))
    # ── TI Subscription plans, LEAD ──
    story.append(Paragraph('Threat Intelligence Subscription, Start Here', s['h2']))
    story.append(md_inline(
        'The TI subscription is the primary RelayShield API product for MSPs and MSSPs. It provides '
        'unlimited access to the full IOC corpus, threat actor intelligence, trending threats, and '
        'STIX/TAXII or MISP feed, everything your team needs to enrich alerts, run investigations, and brief clients. '
        '<b>Enterprise TI platforms charge $30K to $300K/year for equivalent coverage. '
        'RelayShield delivers 500K+ distinct queryable indicators, backed by 5.8M+ citations, at $499/month.</b>',
        s['body']))
    story.append(Spacer(1, 6))

    # Subscription plan cards
    TEAL_DARK  = colors.HexColor('#008F82')
    NAVY_LIGHT = colors.HexColor('#1A3A5C')
    GREEN_BG   = colors.HexColor('#E6F7F5')
    BLUE_BG    = colors.HexColor('#EAF0F8')

    def _card_para(text, bold=False, color=BLACK, size=9):
        sty = ParagraphStyle('cp', fontName='Helvetica-Bold' if bold else 'Helvetica',
            fontSize=size, textColor=color, leading=13, spaceAfter=2, spaceBefore=2, wordWrap='CJK')
        return Paragraph(text, sty)

    # Two-column plan cards
    starter_items = [
        _card_para('TI STARTER', bold=True, color=WHITE, size=10),
        _card_para('$499 / month', bold=True, color=WHITE, size=13),
        _card_para('10,000 API calls/month', color=WHITE),
        _card_para(' '),
        _card_para('✓  500K+ indicator corpus query', color=WHITE),
        _card_para('✓  Bulk IOC lookup (100/batch)', color=WHITE),
        _card_para('✓  IOC pivot & lateral discovery', color=WHITE),
        _card_para('✓  Early Warning Intelligence', color=WHITE),
        _card_para('✓  MITRE ATT&CK actor profiles', color=WHITE),
        _card_para('✓  Trending threats (24hr)', color=WHITE),
        _card_para('✓  STIX/TAXII 2.1 + MISP feed', color=WHITE),
        _card_para('✓  Shareable report links', color=WHITE),
        _card_para('✓  Brand monitor', color=WHITE),
        _card_para('✓  Third-party risk score', color=WHITE),
        _card_para('✓  All 26 identity endpoints', color=WHITE),
        _card_para(' '),
        _card_para('Best for: MSPs building SIEM/SOAR', color=colors.HexColor('#B0D4D0')),
    ]
    unlimited_items = [
        _card_para('TI UNLIMITED', bold=True, color=WHITE, size=10),
        _card_para('$999 / month', bold=True, color=WHITE, size=13),
        _card_para('Unlimited calls, no quota gate', color=WHITE),
        _card_para(' '),
        _card_para('✓  Everything in TI Starter', color=WHITE),
        _card_para('✓  No monthly call cap', color=WHITE),
        _card_para('✓  Priority SLA', color=WHITE),
        _card_para('✓  Weekly MSP threat digest email', color=WHITE),
        _card_para('✓  STIX/TAXII continuous pull', color=WHITE),
        _card_para('✓  Bulk S3/Kinesis export (coming)', color=WHITE),
        _card_para(' '),
        _card_para(' '),
        _card_para(' '),
        _card_para(' '),
        _card_para(' '),
        _card_para('Best for: MSSPs with high query volume', color=colors.HexColor('#B0C8D4')),
    ]

    card_table = Table(
        [[Table([[i] for i in starter_items],
                colWidths=[3.4*inch],
                style=TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), TEAL_DARK),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ('TOPPADDING', (0,0), (-1,-1), 3),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                    ('ROUNDEDCORNERS', [6, 6, 6, 6]),
                ])),
         Table([[i] for i in unlimited_items],
                colWidths=[3.4*inch],
                style=TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), NAVY_LIGHT),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                    ('TOPPADDING', (0,0), (-1,-1), 3),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                    ('ROUNDEDCORNERS', [6, 6, 6, 6]),
                ]))]],
        colWidths=[3.55*inch, 3.55*inch],
        style=TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ])
    )
    story.append(KeepTogether([card_table, Spacer(1, 6)]))

    story.append(md_inline(
        'Self-serve signup: <b>api.relayshield.net/developers</b>, instant API key, no sales call, cancel anytime.',
        s['small']))
    story.append(Spacer(1, 6))

    story.append(md_inline(
        '**Procure through AWS Marketplace instead, if that is easier:** RelayShield is an AWS Marketplace '
        'seller (AWS account 239677749008), so an MSP with an existing AWS agreement can buy on their AWS '
        'bill, draw down committed spend, and skip a new vendor onboarding entirely. Three listings are live:',
        s['body']))
    story.append(Spacer(1, 4))

    mkt_rows = [
        ['Listing', 'What it covers', 'Shape'],
        ['Threat Intelligence -\nStarter / Unlimited',
         'The full IOC corpus over STIX/TAXII 2.1 and MISP, plus the TI query endpoints',
         'Flat-rate monthly subscription'],
        ['Core Identity Exposure\n(Bundle A)',
         'Six identity endpoints: breach exposure, SIM swap detection, infostealer log checks, '
         'domain lookalike detection, OAuth token exposure watchlist, crypto threat intelligence',
         'Monthly minimum commitment plus metered usage per endpoint'],
        ['Agentic Attack Surface\n(Bundle D)',
         'Five agent-era endpoints: MCP registry risk, prompt-injection breach correlation, '
         'agent-framework CVE targeting, bulk per-agent identity risk scoring, LLM credential '
         'exposure detection',
         'Metered usage per endpoint'],
    ]
    _mc = ParagraphStyle('mktcell', fontName='Helvetica', fontSize=7.4, leading=9.4)
    _mh = ParagraphStyle('mkthead', fontName='Helvetica-Bold', fontSize=7.4, leading=9.4,
                         textColor=colors.white)
    mkt_table = Table(
        [[Paragraph(c.replace('\n', '<br/>'), _mh if i == 0 else _mc) for c in row]
         for i, row in enumerate(mkt_rows)],
        colWidths=[1.35*inch, 4.0*inch, 1.95*inch],
    )
    mkt_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F3A5F')),
        ('GRID',       (0,0), (-1,-1), 0.4, colors.HexColor('#D1D9E6')),
        ('VALIGN',     (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING',(0,0), (-1,-1), 5),
        ('RIGHTPADDING',(0,0),(-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F4F7FB')]),
    ]))
    story.append(KeepTogether([mkt_table, Spacer(1, 5)]))

    story.append(md_inline(
        'Each bundle is licensed independently, with no dependency on any other bundle or on the direct '
        'subscription. Your API key is issued automatically by email when the subscription activates. '
        '**For AWS-native MSPs this is usually the shortest path to a signature** - Marketplace procurement '
        'runs through an approval process the client\'s finance team already has, which removes the "new '
        'vendor" objection that stalls small security purchases more often than price does.',
        s['small']))
    story.append(Spacer(1, 8))

    # ── Capability cards ──
    story.append(Paragraph('What the TI Subscription Covers', s['h2']))

    CAP_TEAL  = colors.HexColor('#E6F7F5')
    CAP_BLUE  = colors.HexColor('#EAF0F8')
    CAP_GOLD  = colors.HexColor('#FDF6E3')
    CAP_RED   = colors.HexColor('#FEF0EE')

    def _cap_header(text, bg):
        sty = ParagraphStyle('ch', fontName='Helvetica-Bold', fontSize=9,
            textColor=NAVY, leading=12, spaceAfter=3, spaceBefore=3)
        return Table([[Paragraph(text, sty)]],
            colWidths=[3.4*inch],
            style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), bg),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))

    def _cap_body(lines, bg):
        def _p(t): return Paragraph(t, ParagraphStyle('cb', fontName='Helvetica',
            fontSize=8.5, textColor=BLACK, leading=12, spaceAfter=1))
        rows = [[_p('• ' + l)] for l in lines]
        return Table(rows, colWidths=[3.4*inch],
            style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), WHITE),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LINEBELOW', (0,-1), (-1,-1), 0.5, colors.HexColor('#D1D9E6')),
                ('LINEBEFORE', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D9E6')),
                ('LINEAFTER', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D9E6')),
            ]))

    cap_rows = [
        # Row 1
        [Table([
            [_cap_header('IOC Corpus & Bulk Enrichment', CAP_TEAL)],
            [_cap_body([
                '500K+ distinct indicators (5.8M+ citations)',
                '20 live feeds + 85+ criminal Telegram channels',
                '3,750+ malware families with ATT&CK attribution',
                '500K is the corpus; 5.8M is how often we have seen it',
                'Bulk lookup: 100 IOCs per api call',
                'IOC pivot: find related C2 infrastructure by malware family',
                '365-day retention',
            ], CAP_TEAL)],
         ], colWidths=[3.4*inch], style=TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)])),
         Table([
            [_cap_header('Early Warning Intelligence', CAP_BLUE)],
            [_cap_body([
                'CVE PoC chatter in criminal channels, 24 to 72 hour pre-NVD warning',
                'CISA KEV: 1,600+ actively-exploited CVEs, daily refresh',
                'Ransomware-campaign-linked CVEs flagged separately',
                'Trending threats: top IOCs spreading in last 24 hours',
                'Threat actor profiles: TTPs, targets, associated IOCs',
                'MITRE ATT&CK: 189 groups, 858 techniques',
            ], CAP_BLUE)],
         ], colWidths=[3.4*inch], style=TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))],
        # Row 2
        [Table([
            [_cap_header('Identity & Credential Intelligence', CAP_GOLD)],
            [_cap_body([
                'Breach exposure: 15B+ credential corpus',
                'Infostealer logs: 3,750+ malware families tracked',
                'Session hijack detection: stolen cookies in stealer archives',
                'Identity graph: email → phone/domain correlation from dumps',
                'NHI exposure: API keys & tokens in stealer logs',
                'Target risk score: 6-signal composite per domain',
            ], CAP_GOLD)],
         ], colWidths=[3.4*inch], style=TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)])),
         Table([
            [_cap_header('Vendor & Brand Protection', CAP_RED)],
            [_cap_body([
                'Third-party risk score: vendor breach + stealer + dark web ($0.10)',
                'Brand monitor: scan the full IOC corpus for brand patterns ($0.35)',
                'Domain lookalike / typosquat scanning ($0.30)',
                'OAuth supply chain: 31 high-risk SaaS apps monitored ($0.30)',
                'Secret scan: secrets already published across GitHub, npm, PyPI, Docker Hub and Hugging Face ($0.35)',
                'STIX/TAXII 2.1 + MISP: direct feed into Splunk, Sentinel, Elastic, or MISP-based SOC tooling',
                'Shareable report links: persistent, public-view URLs for any scan result',
            ], CAP_RED)],
         ], colWidths=[3.4*inch], style=TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))]
    ]
    cap_table = Table(cap_rows, colWidths=[3.55*inch, 3.55*inch],
        style=TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
    story.append(KeepTogether([cap_table, Spacer(1, 8)]))

    # ── Crypto asset intelligence ──
    story.append(md_inline('**Crypto Asset Intelligence, Cross-Surface Attack Detection:**', s['body']))
    story.append(md_inline(
        'The /v1/crypto-intel endpoint goes beyond a simple lookup. When it flags a wallet counterparty '
        'as high risk, RelayShield records that signal in the same 72-hour correlation window as identity '
        'signals. A SIM swap alert and a flagged wallet transaction arriving within 72 hours is the most common '
        'crypto exchange drain pattern. <b>No competitor has both signal streams and the correlation layer '
        'to connect them.</b>',
        s['body']))
    story.append(Spacer(1, 8))

    # ── Individual endpoints, ad-hoc note ──
    story.append(Paragraph('Individual API Endpoints, Ad-Hoc & Low-Volume Testing', s['h2']))
    story.append(md_inline(
        '<b>Note: Individual per-call endpoints are intended for low-volume ad-hoc testing and evaluation only. '
        'Production integrations and MSP workflows should use the TI Starter or TI Unlimited subscription '
        ',  which provides the same endpoints at a predictable monthly cost with no per-call overhead.</b>',
        ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=9, textColor=NAVY,
            leading=13, spaceAfter=6, spaceBefore=4,
            borderColor=TEAL, borderWidth=1, borderPad=8, backColor=GREEN_BG)))
    story.append(Spacer(1, 4))
    story.append(md_inline('Selected endpoints available for testing ($0.10 to $0.50/call):', s['body']))
    for ep in [
        'POST /v1/metered/breach, credential breach lookup ($0.10)',
        'POST /v1/metered/sim-swap, real-time SIM swap check ($0.25)',
        'POST /v1/metered/domain, domain lookalike scan ($0.30)',
        'POST /v1/metered/infostealer, infostealer log exposure ($0.50)',
        'POST /v1/metered/supply-chain, vendor third-party risk score ($0.10, up to 10 domains)',
        'POST /v1/metered/brand-monitor: brand mention scan in IOC corpus ($0.35)',
        'POST /v1/metered/bulk-ioc, bulk IOC enrichment, up to 100 per call ($0.50/batch)',
        'POST /v1/metered/bulk-identity-risk, hierarchical org + agent risk: up to 10 domains + 5 agent emails each ($2.00/call)',
        'GET /v1/intel/cve, CISA KEV lookup by CVE ID or keyword',
    ]:
        story.append(md_inline('• ' + ep, s['bullet']))
    story.append(Spacer(1, 4))
    story.append(md_inline(
        'PAYG x402 also available for zero-commitment testing: pay per call in USDC on Base, '
        'no API key, no signup required. See api.relayshield.net/developers.',
        s['small']))
    story.append(Spacer(1, 6))

    story.append(md_inline(
        '**Mid-market MSSP feed (coming):** A bulk S3/Kinesis export tier ($1,500 to $3,000/mo) for MSSPs '
        'running RelayShield data through their own SIEM/SOAR pipeline at scale across many client tenants. '
        'Contact us to join early access.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**Drops into the SIEM your clients already run:** RelayShield\'s IOC corpus is served over '
        'STIX/TAXII 2.1 and MISP, so it ingests through Elastic Security\'s built-in Threat Intel '
        'integrations and Microsoft Sentinel\'s first-party Threat Intelligence - TAXII data connector '
        'with configuration alone - no connector to build and no professional-services '
        'engagement. Splunk HEC, CEF/QRadar and Cortex XSOAR are supported as push destinations. For an '
        'MSSP running a shared SIEM across client tenants, this removes the integration objection entirely.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**Microsoft Sentinel, specifically:** point the **Threat Intelligence - TAXII** connector at API '
        'root <b>https://api.relayshield.net/v1/intel/taxii/</b> with collection ID <b>iocs</b>, and '
        'indicators land in Sentinel\'s ThreatIntelIndicators table ready for analytics rules, hunting '
        'queries and incident enrichment. Two things are worth knowing before the first attempt, because '
        'both look like a bad API key when they are not: put your key in **both** the Username and Password '
        'fields (Sentinel\'s TAXII client skips authentication when the password is empty), and target '
        'ThreatIntelIndicators, **not** the legacy ThreatIntelligenceIndicator table, which retired on '
        '31 May 2026 and silently matches nothing. Full walkthrough, including KQL for IP, domain and '
        'malware-family rules, is in the Sentinel integration guide.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**Live automation, not just an API:** RelayShield\'s employee-offboarding credential check is a '
        'published, officially-approved template in n8n\'s workflow library (n8n.io/workflows/16694), an HR '
        'webhook triggers three parallel identity-risk checks (breach, infostealer, OAuth token exposure) the '
        'moment someone\'s offboarded, routing findings to Slack, a manager email summary, and a Notion audit '
        'log automatically. This isn\'t a hypothetical integration path. It\'s live, installable today, built '
        'on the same API MSPs get direct access to above.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**Zapier, for the no-code half of your client base:** RelayShield has passed Zapier\'s review '
        'process and is published in the **Zapier App Directory**, which connects the same identity checks '
        'to 8,000+ apps with no code at all. For an MSP, the practical shape is a client-facing workflow '
        'the client can own: a new-hire row in a Google Sheet or an HR tool triggers a breach and '
        'infostealer check; a hit posts to a Slack channel and opens a ticket in the PSA you already run. '
        'Nothing to host, nothing to maintain, and it survives the client changing their HR stack.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**Ansible, for the MSPs who automate their fleet properly:** the <b>relayshield.security</b> '
        'collection is published on **Ansible Galaxy** under RelayShield\'s own <b>relayshield</b> '
        'namespace, so identity checks run as ordinary tasks inside the playbooks you already use for '
        'onboarding, offboarding and patch cycles:',
        s['body']))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        '<font face="Courier" size="8.5">ansible-galaxy collection install relayshield.security</font>',
        ParagraphStyle('ansiblecmd', fontName='Courier', fontSize=8.5, leading=12,
                       leftIndent=10, spaceBefore=2, spaceAfter=4,
                       backColor=colors.HexColor('#F4F7FB'))))
    story.append(md_inline(
        'Requires Ansible >= 2.15.0. The collection screens email addresses for breach and infostealer '
        'exposure, detects lookalike domains, and checks vendor domains for supply chain risk - **before a '
        'play grants access or deploys**. That ordering is the point: a gate inside the playbook stops a '
        'provisioning run against an already-compromised identity, rather than reporting it afterwards.',
        s['body']))
    story.append(Spacer(1, 6))
    story.append(md_inline(
        '**All three automation surfaces are published and installable today** - n8n, Zapier and Ansible '
        'Galaxy. Nothing in this section is a roadmap item.',
        s['small']))

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
        [_pe('Zero friction'), _pe('WhatsApp/Telegram delivery. Clients onboard in under 5 minutes, no MSP involvement after referral')],
        [_pe('Instant credibility'), _pe('First alert proves value immediately. Clients see a real breach or risk on day one')],
        [_pe('Recurring MRR'), _pe('Monthly per-account subscription. Predictable, stackable revenue')],
        [_pe('Natural upsell'), _pe('Pairs with any existing endpoint, backup, or antivirus contract, not a replacement')],
        [_pe('Carrier-level differentiation'), _pe('SIM swap monitoring at carrier depth. No competitor offers this at SMB pricing')],
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
        'RelayShield closes that gap, monitoring every credential, phone number, domain, and infostealer log '
        'in real time, correlating signals across the full attack surface, and alerting your clients '
        'while the attack is still forming. Not after the damage is done."', s['quote']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Day one ──
    story.append(Paragraph('What Your Clients Get on Day One', s['h2']))
    for i, item in enumerate([
        'Immediate breach check on all monitored email addresses',
        'Infostealer log scan, credentials checked against criminal market exposure',
        'SIM swap monitoring activated on all registered phone numbers',
        'Domain lookalike scan across 500M+ registered domains',
        'OAuth & token exposure audit, breach watchlist + live stealer log corpus; rogue app detection active',
        'Predictive attack chain engine active, correlation monitoring begins immediately across 11 chains',
        'Cross-surface correlation live, identity signals correlated against crypto wallet risk signals for clients with digital asset exposure',
        'Step-by-step remediation guidance built into every alert',
    ], 1):
        story.append(md_inline(f'<b>{i}.</b>  {item}', s['bullet']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=2))

    # ── Getting started ──
    story.append(Paragraph('Getting Started', s['h2']))
    for label, body in [
        ('Pilot program:', 'Free 30-day Business Starter + Domain account for the MSP principal, full feature access for a single seat. No team seats, no commitment required.'),
        ('Onboarding:', 'Clients self-onboard via a 2-minute WhatsApp or Telegram flow. No MSP involvement required after the initial referral.'),
        ('Support:', 'Direct line to RelayShield founder for all partner questions.'),
    ]:
        story.append(md_inline(f'<b>{label}</b> {body}', s['body']))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#D1D9E6'), spaceAfter=6))

    # ── Contact ──
    story.append(Paragraph('Contact', s['h2']))
    story.append(Paragraph('Andrew Gibbs, Founder, RelayShield', s['contact_name']))
    story.append(Paragraph('relayshieldadmin@gmail.com  ·  relayshield.net', s['contact']))
    story.append(Paragraph('Andover, MA  ·  RelayShield LLC (Est. April 2026)', s['contact']))
    story.append(Paragraph('25 years in telecommunications security. Built on a carrier-layer detection foundation no competitor has replicated.', s['contact']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'RelayShield is a registered business in the Commonwealth of Massachusetts (ID: 001963633).',
        s['small']))

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f'✅  {output_path}')


# ─── AGENTCORE POC ONE-PAGER ──────────────────────────────────────────────────

def build_agentcore_onepager(output_path):
    """External leave-behind for AWS partner/channel conversations.

    Deliberately excludes the INTERNAL NOTES block carried in
    RelayShield_AgentCore_POC_OnePager.md -- that is working context for the
    founder (stale-stat warnings, the AgentCore Preview-vs-GA correction) and
    must never reach a recipient.
    """
    s = dict(make_styles())
    # Local overrides: this is a genuine one-pager, so headings and body run
    # tighter than the multi-page briefs. Copied rather than mutated so the
    # shared styles stay untouched for the other builders.
    s['h2'] = ParagraphStyle('h2_oc', parent=s['h2'], fontSize=12, leading=15,
                             spaceBefore=7, spaceAfter=3)
    s['body'] = ParagraphStyle('body_oc', parent=s['body'], fontSize=9.3,
                               leading=12.4, spaceAfter=4, spaceBefore=1)
    s['bullet'] = ParagraphStyle('bullet_oc', parent=s['bullet'], fontSize=9.3,
                                 leading=12.4, spaceAfter=2, spaceBefore=0)
    margins = dict(leftMargin=0.56*inch, rightMargin=0.56*inch,
                   topMargin=1.16*inch, bottomMargin=0.42*inch)

    HDR_TITLE    = 'Autonomous Agent-to-API Commerce on AWS'
    HDR_SUBTITLE = 'RelayShield x Amazon Bedrock AgentCore - end-to-end proof of concept'

    def first_page(canvas, doc):
        header_band(canvas, doc, HDR_TITLE, HDR_SUBTITLE)
    def later_pages(canvas, doc):
        page_header_footer(canvas, doc, 'AgentCore Proof of Concept')

    doc = SimpleDocTemplate(output_path, pagesize=letter, **margins)
    story = []

    story.append(Paragraph('What We Set Out to Prove', s['h2']))
    story.append(md_inline(
        'That an autonomous AI agent could **discover, pay for, and consume a live commercial API** with no '
        'human in the loop, no pre-provisioned API key, and no prior relationship between agent and vendor - '
        'using real money, on production infrastructure, entirely on AWS-native tooling.',
        s['body']))
    story.append(md_inline('**Not a sandbox. Not a testnet. Not a scripted demo.**', s['body']))

    story.append(Paragraph('What We Built', s['h2']))
    rows = [
        ['Layer', 'Component'],
        ['Discovery', 'AgentCore Gateway with the CDP x402 Bazaar as a native MCP server target - zero custom discovery code'],
        ['Payments', 'AgentCore Payments - credential provider, payment manager, connector and embedded CDP wallet, via boto3'],
        ['Agent', 'Strands agent on Bedrock (Claude Sonnet) using the AgentCorePaymentsPlugin for automatic HTTP 402 handling'],
        ['Settlement', 'Real USDC on Base mainnet, signed via CDP delegated signing'],
        ['Target API', "RelayShield's identity-risk-score endpoint - a live, commercially listed AWS Marketplace product"],
    ]
    t = Table([[Paragraph(c, s['small']) for c in r] for r in rows],
              colWidths=[1.0*inch, 5.85*inch])
    # compact variant of table_style() -- same look, less vertical padding, so
    # the whole brief stays on a single page
    ts = table_style()
    ts.add('TOPPADDING', (0, 0), (-1, -1), 3)
    ts.add('BOTTOMPADDING', (0, 0), (-1, -1), 3)
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 2))

    story.append(Paragraph('What Happened', s['h2']))
    story.append(md_inline('The agent was given a task and a funded wallet. Unassisted, it:', s['body']))
    for i, step in enumerate([
        "Searched the x402 Bazaar and located RelayShield's identity-risk endpoint",
        'Called it and received an HTTP 402 Payment Required',
        'Signed and settled the payment on-chain',
        'Retried, received the real scored result, and summarized it correctly',
    ], 1):
        story.append(md_inline(f'{i}.  {step}', s['bullet']))
    story.append(Spacer(1, 2))
    story.append(md_inline(
        '**On-chain proof:** 0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016 - '
        'Base mainnet, status success, verified via direct RPC. The entire loop, discovery through '
        'settlement through consumption, ran without human intervention.',
        s['body']))

    story.append(Paragraph('Why This Matters', s['h2']))
    for label, text in [
        ('For AWS.', 'The agentic-commerce loop closing end to end on AWS-native services, against a real '
                     'Marketplace ISV rather than a reference implementation. Every layer is AWS.'),
        ('For the telco channel.', 'The pattern generalises to machine-to-machine service consumption: an '
                     'autonomous system procuring a metered capability on demand and settling per-call, with '
                     'no contract negotiation or credential provisioning step. That is the shape of network '
                     'function chaining, roaming settlement and wholesale interconnect, with the procurement '
                     'friction removed.'),
        ('For RelayShield.', 'An AWS Marketplace seller since June 2026 - this proves our endpoints are '
                     'consumable by autonomous agents today, not on a roadmap.'),
    ]:
        story.append(md_inline(f'**{label}** {text}', s['body']))

    story.append(Paragraph('About RelayShield', s['h2']))
    for line in [
        '**500K+ distinct indicators of compromise**, drawn from **5.8M+ citations** across criminal Telegram marketplaces and 11 authoritative feeds',
        '**85+ monitored criminal channels** - typically 24-72 hours ahead of public breach databases',
        '**3,750+ tracked malware families**',
        '**26 identity endpoints** - breach, infostealer, SIM swap, OAuth and domain exposure, non-human identity, LLM credential exposure',
        'Live on AWS Marketplace (prod-kb3ftelx44wlk), AWS account 239677749008; STIX/TAXII 2.1 and MISP feeds available',
    ]:
        story.append(md_inline('\u2022  ' + line, s['bullet']))

    story.append(Paragraph('What We Are Looking For', s['h2']))
    story.append(md_inline(
        'An introduction to the AgentCore product team or the AWS Partner org. We would value being an '
        'early-adopter reference for agentic commerce, and guidance on our path toward ISV Accelerate '
        '(Partner Central verification is complete). Happy to walk through the technical detail or demo live.',
        s['body']))
    story.append(Paragraph('support@relayshield.net  |  api.relayshield.net/developers', s['contact_name']))

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f'\u2705  {output_path}')


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


# ─── SOLANA MOBILE GRANT PITCH DECK ────────────────────────────────────────────

def build_solana_grant(output_path):
    s = make_styles()
    w, h = letter
    margins = dict(leftMargin=0.6*inch, rightMargin=0.6*inch,
                   topMargin=1.35*inch, bottomMargin=0.75*inch)

    HDR_TITLE    = 'Crypto Shield Mobile'
    HDR_SUBTITLE = 'Solana Mobile Grant Application — RelayShield'

    def first_page(canvas, doc):
        header_band(canvas, doc, HDR_TITLE, HDR_SUBTITLE)
    def later_pages(canvas, doc):
        page_header_footer(canvas, doc, 'Solana Mobile Grant Application')

    doc = SimpleDocTemplate(output_path, pagesize=letter, **margins)
    story = []

    # Mission / hook
    story.append(Paragraph('The Problem', s['h2']))
    story.append(Paragraph(
        'Every competing wallet-security product watches on-chain activity only. '
        'Most real attacks start off-chain — a leaked password, a phished session, a SIM-swap — '
        'long before a malicious transaction ever gets signed.',
        s['quote']))
    story.append(md_inline(
        'Wallet drainers, address poisoning, and fake NFT mints get the headlines, but the credential '
        'layer is where most attacks actually begin. A user\'s email is breached, their session is hijacked, '
        'or their SIM is swapped — and by the time a malicious transaction reaches the chain, the attacker '
        'has already done the hard part. Existing wallet security tools have no visibility into any of this.',
        s['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('The Solution — Crypto Shield Mobile', s['h2']))
    story.append(md_inline(
        'Crypto Shield Mobile is the only consumer product that treats the credential layer and the chain '
        'layer as one attack surface. It is a **native Android app** — not a wrapped web dashboard — that '
        'provides **read-only** wallet security monitoring across Solana, EVM (including Base), TON, Bitcoin, '
        'and XRP. It never requests a seed phrase or private key access; it cannot move funds.',
        s['body']))
    story.append(Spacer(1, 4))
    story.append(Paragraph('Core capabilities:', s['body']))
    for line in [
        '<b>Wallet risk scanning</b> — instant risk scoring for wallets, tokens, and NFTs across every supported chain.',
        '<b>Address poisoning detection</b> — catches look-alike addresses attackers use to trick users into copying the wrong one from transaction history.',
        '<b>NFT Security scanning</b> — flags malicious or fake NFT contracts, including drainer contracts disguised as reward NFTs.',
        '<b>Criminal Telegram intelligence</b> — 37+ monitored channels where stolen data and drainer kits are traded, surfacing threats 24-72 hours before public disclosure.',
        '<b>Mobile Wallet Adapter integration</b> — read-only wallet connect (authorize only, never signing) that auto-populates a monitored Solana address instead of manual entry.',
        '<b>Signature Guard</b> — approval monitoring, transaction simulation before signing, and session hijack detection.',
    ]:
        story.append(md_inline(line, s['bullet']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('Platform & Traction', s['h2']))
    story.append(md_inline(
        'Crypto Shield Mobile is built on RelayShield, a live threat-intelligence platform with real, '
        'paying customers on its B2A API today — not a project starting from zero.',
        s['body']))
    for line in [
        '<b>2M+ indicator</b> IOC corpus across 20+ feed sources, 365-day retention.',
        '<b>37+ monitored criminal Telegram channels</b> — infostealer log markets, credential dump channels, SIM-swap service listings.',
        'Live B2A REST API with metered and flat-rate subscription tiers, active paying subscribers.',
        'STIX/TAXII 2.1 and MISP feed export — SOAR/SIEM-ready threat intelligence.',
        '<b>Solana-native x402 micropayments</b> — all metered API endpoints support pay-per-call access via x402 with USDC on Solana, including a CDP-sponsored fee-payer that covers gas for every SVM transaction, so callers never need a funded Solana wallet.',
        'Crypto Shield Mobile v1.3.0 submitted to the Solana dApp Store (Mobile Wallet Adapter integration, NFT security scanning, Jupiter token verification, address poisoning detection).',
    ]:
        story.append(md_inline(line, s['bullet']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('Roadmap', s['h2']))
    for status, line in [
        ('Shipped', 'Mobile Wallet Adapter — read-only Connect Wallet, auto-populated Solana address'),
        ('Next', 'Solana Blinks/Actions security scanning — verify shareable transaction links before signing'),
        ('Planned', 'Ecosystem integration — token/NFT risk API + embeddable security badges for Solana dApps, DEXs, marketplaces'),
        ('Later', 'Google Play onboarding — same APK, broader Android distribution'),
        ('Later', 'iOS App Store release — Solana wallet monitoring continues; native MWA connect is Android-only'),
    ]:
        story.append(md_inline(f'<b>[{status}]</b> {line}', s['bullet']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('Public Good Commitment', s['h2']))
    story.append(md_inline(
        'RelayShield already operates two public-good pieces of infrastructure directly relevant to the '
        'Solana ecosystem: a free, embeddable color-coded security badge that any Solana dApp, DEX, or NFT '
        'marketplace can drop into their own site to show a live risk signal for a domain, and a URL/link '
        'reputation scanner directly applicable to the phishing-link problem endemic to Solana airdrops and '
        'fake mint pages. As part of this grant, RelayShield commits to offering free API access to both '
        'capabilities specifically for Solana ecosystem projects, rather than gating them behind standard '
        'commercial API pricing. Longer-term, RelayShield is exploring extending its existing Solana-native '
        'x402 payment rail to agentic commerce use cases with other Solana-native projects.',
        s['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('Team', s['h2']))
    story.append(md_inline(
        'RelayShield is founded and operated by Andrew Gibbs, drawing on 25 years of telecom security '
        'experience. RelayShield is self-funded and profitable on its core API business, with Crypto Shield '
        'Mobile extending the same threat-intelligence pipeline into a native wallet-security app.',
        s['body']))
    story.append(Spacer(1, 6))

    story.append(Paragraph('The Ask', s['h2']))
    story.append(md_inline(
        'Requesting <b>$10,000-$20,000</b> to fund the Solana Blinks/Actions security scanning feature '
        '(the next scoped engineering milestone, extending the existing Signature Guard transaction-simulation '
        'approach to this newer attack surface) and initial ecosystem-integration outreach to Solana DeFi, '
        'NFT, and RWA platforms for the badge/API distribution described above.',
        s['body']))

    doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    print(f'✅  {output_path}')


if __name__ == '__main__':
    base = '/Users/andrewgibbs/Side SaaS Hustle'
    build_msp(f'{base}/RelayShield_MSP_Solution_Brief.pdf')
    build_exec(f'{base}/RelayShield_Executive_Briefing.pdf')
    build_solana_grant(f'{base}/crypto-shield-app/RelayShield_Solana_Grant_Pitch_Deck.pdf')
    build_agentcore_onepager(f'{base}/RelayShield_AgentCore_POC_OnePager.pdf')
