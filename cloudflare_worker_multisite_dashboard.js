// RelayShield Multi-Site Shield — Tex-Mex Group Demo Dashboard
// Deploy: wrangler deploy cloudflare_worker_multisite_dashboard.js --name relayshield-multisite-demo

const DEMO_TOKEN = "rs-multisite-2026";

const LOCATIONS = [
  { id: "austin-1",    name: "Austin — South Congress",  city: "Austin, TX",      score: 78, grade: "F", risk: "CRITICAL", employees: 6,  alerts: 2, infostealer: 2, breach: 3, simswap: 1, lookalike: 1, daysSince: 0  },
  { id: "austin-2",    name: "Austin — Domain",          city: "Austin, TX",      score: 71, grade: "F", risk: "CRITICAL", employees: 5,  alerts: 1, infostealer: 1, breach: 2, simswap: 1, lookalike: 0, daysSince: 2  },
  { id: "dallas-1",    name: "Dallas — Uptown",          city: "Dallas, TX",      score: 42, grade: "D", risk: "HIGH",     employees: 7,  alerts: 1, infostealer: 0, breach: 4, simswap: 0, lookalike: 1, daysSince: 8  },
  { id: "plano",       name: "Plano — Legacy",           city: "Plano, TX",       score: 38, grade: "D", risk: "HIGH",     employees: 5,  alerts: 1, infostealer: 0, breach: 2, simswap: 0, lookalike: 1, daysSince: 12 },
  { id: "houston-1",   name: "Houston — Montrose",       city: "Houston, TX",     score: 22, grade: "C", risk: "MEDIUM",   employees: 8,  alerts: 0, infostealer: 1, breach: 1, simswap: 0, lookalike: 0, daysSince: 18 },
  { id: "houston-2",   name: "Houston — Heights",        city: "Houston, TX",     score: 18, grade: "C", risk: "MEDIUM",   employees: 6,  alerts: 0, infostealer: 0, breach: 2, simswap: 0, lookalike: 0, daysSince: 22 },
  { id: "san-antonio", name: "San Antonio — Pearl",      city: "San Antonio, TX", score: 12, grade: "B", risk: "LOW",      employees: 6,  alerts: 0, infostealer: 0, breach: 1, simswap: 0, lookalike: 0, daysSince: 31 },
  { id: "ft-worth",    name: "Fort Worth — Sundance",    city: "Fort Worth, TX",  score: 9,  grade: "A", risk: "LOW",      employees: 5,  alerts: 0, infostealer: 0, breach: 1, simswap: 0, lookalike: 0, daysSince: 44 },
];

const ALERTS = [
  { loc: "Austin — South Congress", locId: "austin-1", level: "CRITICAL", type: "Infostealer",    identity: "manager@austinsoco.texmexgroup.com", detail: "RedLine Stealer log published 6h ago. Session cookies extracted for Square POS + Gmail. Rotate credentials immediately.", ago: "6h ago" },
  { loc: "Austin — South Congress", locId: "austin-1", level: "CRITICAL", type: "SIM Swap",       identity: "+1 (512) 555-0147",                  detail: "Carrier-layer port request detected at T-Mobile for this number. Block recommended immediately. Phone associated with POS admin access.", ago: "22m ago" },
  { loc: "Austin — Domain",         locId: "austin-2", level: "CRITICAL", type: "Session Cookie", identity: "ops@austindomain.texmexgroup.com",    detail: "Active session cookie found in stealer archive — QuickBooks Online + Gusto Payroll. 2FA bypass possible with this token.", ago: "14h ago" },
  { loc: "Dallas — Uptown",         locId: "dallas-1", level: "HIGH",     type: "Breach",         identity: "manager@dallasuptown.texmexgroup.com",detail: "Appears in LinkedIn 2024 breach (560M records). Password reuse risk: Square, Gmail, Gusto. Schedule rotation.", ago: "8d ago" },
  { loc: "Plano — Legacy",          locId: "plano",    level: "HIGH",     type: "Lookalike Domain",identity: "texmex-group-billing.com",           detail: "Lookalike domain registered 3 days ago. Matches your business domain. Potential vendor impersonation / invoice fraud setup.", ago: "3d ago" },
];

const LOCATION_DETAILS = {
  "austin-1": {
    dimensions: { breach_exposure: 25, infostealer_density: 25, session_exposure: 10, cve_exposure: 8, ioc_presence: 5, ransomware_victim: 5 },
    identities: [
      { email: "manager@austinsoco.texmexgroup.com",  level: "CRITICAL", score: 92, finding: "RedLine Stealer: Square POS session, Gmail session extracted" },
      { email: "owner@austinsoco.texmexgroup.com",    level: "HIGH",     score: 48, finding: "Appears in 3 breach databases. Password reuse risk." },
      { email: "pos-admin@texmexgroup.com",           level: "HIGH",     score: 44, finding: "NHI: Square API integration key found in credential archive" },
    ],
    timeline: [
      { date: "Jun 26", type: "CRITICAL", event: "Infostealer — RedLine log, 3 credentials extracted" },
      { date: "Jun 26", type: "CRITICAL", event: "SIM Swap attempt — +1(512)555-0147 port request at T-Mobile" },
      { date: "Jun 24", type: "HIGH",     event: "Breach — LinkedIn 2024, manager email found" },
      { date: "Jun 18", type: "HIGH",     event: "Lookalike — texmexsoco-secure.com registered" },
      { date: "Jun 10", type: "MEDIUM",   event: "Breach — Adobe 2024, owner email found" },
    ]
  },
  "austin-2": {
    dimensions: { breach_exposure: 22, infostealer_density: 20, session_exposure: 10, cve_exposure: 10, ioc_presence: 4, ransomware_victim: 5 },
    identities: [
      { email: "ops@austindomain.texmexgroup.com",    level: "CRITICAL", score: 88, finding: "Active session cookie in stealer archive — QuickBooks Online, Gusto Payroll" },
      { email: "manager@austindomain.texmexgroup.com",level: "HIGH",     score: 52, finding: "Infostealer hit — credentials in RedLine archive (48h old)" },
    ],
    timeline: [
      { date: "Jun 25", type: "CRITICAL", event: "Session cookie — QuickBooks + Gusto tokens in stealer archive" },
      { date: "Jun 24", type: "HIGH",     event: "Infostealer — RedLine log, manager credentials" },
      { date: "Jun 20", type: "MEDIUM",   event: "Breach — Dropbox 2023, ops email found" },
    ]
  }
};

function riskColor(level) {
  return level === "CRITICAL" ? "#ef4444" : level === "HIGH" ? "#f97316" : level === "MEDIUM" ? "#facc15" : "#22c55e";
}

function gradeColor(g) {
  return g === "A" ? "#22c55e" : g === "B" ? "#4ade80" : g === "C" ? "#facc15" : g === "D" ? "#f97316" : "#ef4444";
}

function portfolioRisk() {
  const avgScore = Math.round(LOCATIONS.reduce((s, l) => s + l.score, 0) / LOCATIONS.length);
  const level = avgScore >= 70 ? "CRITICAL" : avgScore >= 45 ? "HIGH" : avgScore >= 22 ? "MEDIUM" : "LOW";
  return { avgScore, level };
}

function renderDashboard() {
  const { avgScore, level } = portfolioRisk();
  const critCount = ALERTS.filter(a => a.level === "CRITICAL").length;
  const totalEmployees = LOCATIONS.reduce((s, l) => s + l.employees, 0);
  const totalInfostealer = LOCATIONS.reduce((s, l) => s + l.infostealer, 0);
  const totalBreach = LOCATIONS.reduce((s, l) => s + l.breach, 0);
  const totalSimswap = LOCATIONS.reduce((s, l) => s + l.simswap, 0);
  const totalAlerts = ALERTS.length;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RelayShield — Tex-Mex Group</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#0a0f1e;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}
  .topbar{background:#060b18;border-bottom:1px solid #1e3a5f;padding:14px 28px;display:flex;align-items:center;justify-content:space-between}
  .logo{display:flex;align-items:center;gap:10px}
  .logo-shield{width:28px;height:28px;background:linear-gradient(135deg,#06b6d4,#3b82f6);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:14px}
  .logo-name{font-size:16px;font-weight:700;color:#e2e8f0}
  .logo-sub{font-size:12px;color:#4a7fa5;margin-left:4px}
  .topbar-right{display:flex;align-items:center;gap:16px}
  .critical-badge{background:#ef444420;color:#ef4444;border:1px solid #ef444440;border-radius:20px;padding:4px 12px;font-size:12px;font-weight:700}
  .scan-note{font-size:11px;color:#4a7fa5}
  .main{padding:24px 28px;max-width:1280px;margin:0 auto}
  .section-title{font-size:12px;color:#4a7fa5;font-weight:700;letter-spacing:.8px;text-transform:uppercase;margin-bottom:12px}

  /* KPI strip */
  .kpi-strip{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:24px}
  .kpi-card{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:10px;padding:14px 16px}
  .kpi-label{font-size:11px;color:#4a7fa5;font-weight:600;letter-spacing:.4px;text-transform:uppercase;margin-bottom:6px}
  .kpi-val{font-size:26px;font-weight:700;color:#e2e8f0;line-height:1}
  .kpi-sub{font-size:11px;color:#64748b;margin-top:4px}
  .kpi-card.critical .kpi-val{color:#ef4444}
  .kpi-card.high .kpi-val{color:#f97316}
  .kpi-card.ok .kpi-val{color:#22c55e}

  /* Two-col layout */
  .grid-2{display:grid;grid-template-columns:1fr 380px;gap:20px;margin-bottom:24px}

  /* Location table */
  .loc-table-wrap{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden}
  .loc-table{width:100%;border-collapse:collapse}
  .loc-table thead th{background:#060b18;padding:10px 14px;text-align:left;font-size:11px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid #1e3a5f}
  .loc-table tbody tr{border-bottom:1px solid #1e3a5f1a;cursor:pointer;transition:background .15s}
  .loc-table tbody tr:hover{background:#1e3a5f30}
  .loc-table tbody tr.selected{background:#1e3a5f50;border-left:3px solid #3b82f6}
  .loc-table td{padding:11px 14px;font-size:13px}
  .loc-name{font-weight:600;color:#e2e8f0}
  .loc-city{font-size:11px;color:#64748b;margin-top:1px}
  .score-pill{display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border-radius:12px;font-size:12px;font-weight:700;border:1px solid}
  .alert-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:4px}
  .grade-chip{display:inline-block;width:26px;height:26px;border-radius:50%;border:2px solid;text-align:center;line-height:22px;font-size:12px;font-weight:800}
  .days{font-size:12px;color:#64748b}

  /* Alerts panel */
  .alerts-panel{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden}
  .alerts-header{background:#060b18;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #1e3a5f}
  .alerts-title{font-size:13px;font-weight:700;color:#e2e8f0}
  .alert-item{padding:12px 16px;border-bottom:1px solid #1e3a5f1a}
  .alert-item:last-child{border-bottom:none}
  .alert-row1{display:flex;align-items:center;gap:8px;margin-bottom:4px}
  .alert-badge{padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;border:1px solid;flex-shrink:0}
  .alert-type{font-size:12px;font-weight:600;color:#94a3b8}
  .alert-loc{font-size:11px;color:#64748b}
  .alert-ago{font-size:11px;color:#64748b;margin-left:auto}
  .alert-identity{font-size:12px;color:#e2e8f0;font-family:monospace;margin-bottom:3px}
  .alert-detail{font-size:11px;color:#64748b;line-height:1.5}
  .ack-btn{font-size:10px;color:#3b82f6;border:1px solid #3b82f640;background:#3b82f610;border-radius:8px;padding:2px 8px;cursor:pointer;margin-top:6px;display:inline-block}
  .cw-btn{font-size:10px;color:#22c55e;border:1px solid #22c55e40;background:#22c55e10;border-radius:8px;padding:2px 8px;cursor:pointer;margin-top:6px;display:inline-block;margin-left:6px}

  /* Detail panel */
  .detail-panel{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:12px;padding:20px;margin-bottom:24px;display:none}
  .detail-panel.visible{display:block}
  .detail-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
  .detail-name{font-size:16px;font-weight:700;color:#e2e8f0}
  .close-btn{background:none;border:1px solid #1e3a5f;color:#94a3b8;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px}
  .detail-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
  .dim-row{display:grid;grid-template-columns:140px 1fr 36px;align-items:center;gap:8px;margin-bottom:6px}
  .dim-name{font-size:12px;color:#94a3b8}
  .dim-bar-wrap{background:#0a0f1e;border-radius:3px;height:6px;overflow:hidden}
  .dim-bar{height:100%;border-radius:3px;transition:width .6s}
  .dim-val{font-size:12px;color:#e2e8f0;text-align:right;font-weight:600}
  .identity-row{padding:8px 0;border-bottom:1px solid #1e3a5f1a}
  .identity-row:last-child{border-bottom:none}
  .id-top{display:flex;align-items:center;gap:8px;margin-bottom:3px}
  .id-email{font-size:12px;color:#e2e8f0;font-family:monospace;flex:1;min-width:0;word-break:break-all}
  .id-score{font-size:12px;color:#f97316;font-weight:700}
  .id-finding{font-size:11px;color:#64748b}
  .timeline-row{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid #1e3a5f1a;align-items:flex-start}
  .timeline-row:last-child{border-bottom:none}
  .tl-date{font-size:11px;color:#64748b;min-width:42px}
  .tl-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-top:3px}
  .tl-event{font-size:12px;color:#94a3b8}
  .action-bar{display:flex;gap:8px;margin-top:16px}
  .action-btn{padding:8px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid}
  .btn-wa{background:#25d36620;color:#25d366;border-color:#25d36640}
  .btn-pdf{background:#3b82f620;color:#3b82f6;border-color:#3b82f640}
  .btn-cw{background:#22c55e20;color:#22c55e;border-color:#22c55e40}

  /* Risk trend */
  .trend-section{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:12px;padding:16px;margin-bottom:24px}
  .trend-bars{display:flex;align-items:flex-end;gap:4px;height:60px;margin-top:12px}
  .trend-bar{flex:1;border-radius:3px 3px 0 0;min-width:0;transition:opacity .2s}
  .trend-bar:hover{opacity:.8}
  .trend-labels{display:flex;gap:4px;margin-top:4px}
  .trend-label{flex:1;text-align:center;font-size:9px;color:#4a7fa5}

  .portfolio-row{display:flex;align-items:center;gap:12px;margin-top:12px;padding:12px;background:#060b18;border-radius:8px}
  .port-label{font-size:12px;color:#4a7fa5}
  .port-score{font-size:20px;font-weight:800}
  .port-level{font-size:12px;font-weight:700;padding:2px 8px;border-radius:8px;border:1px solid}
  .port-sub{font-size:11px;color:#64748b;margin-left:auto}

  @media(max-width:900px){.grid-2{grid-template-columns:1fr}.kpi-strip{grid-template-columns:repeat(3,1fr)}.detail-grid{grid-template-columns:1fr 1fr}}

  /* ConnectWise ticket modal */
  .cw-modal-overlay{display:none;position:fixed;inset:0;background:#00000090;align-items:center;justify-content:center;z-index:100}
  .cw-modal-overlay.visible{display:flex}
  .cw-modal{background:#0f1f3a;border:1px solid #1e3a5f;border-radius:14px;padding:24px;width:420px;max-width:90vw;box-shadow:0 20px 60px #00000060}
  .cw-modal-header{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #1e3a5f}
  .cw-modal-check{width:28px;height:28px;border-radius:50%;background:#22c55e20;color:#22c55e;display:flex;align-items:center;justify-content:center;font-weight:800;flex-shrink:0}
  .cw-modal-title{font-size:15px;font-weight:700;color:#e2e8f0}
  .cw-modal-row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1e3a5f1a;font-size:12px}
  .cw-modal-row:last-child{border-bottom:none}
  .cw-modal-label{color:#4a7fa5}
  .cw-modal-val{color:#e2e8f0;font-weight:600;text-align:right}
  .cw-modal-summary{font-size:12px;color:#94a3b8;line-height:1.5;margin-top:12px;padding-top:12px;border-top:1px solid #1e3a5f}
  .cw-modal-close{width:100%;margin-top:18px;padding:10px;border-radius:8px;border:1px solid #1e3a5f;background:#1e3a5f;color:#e2e8f0;font-size:13px;font-weight:600;cursor:pointer}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo">
    <div class="logo-shield">🛡</div>
    <span class="logo-name">RelayShield</span>
    <span class="logo-sub">Multi-Site Shield</span>
    <span style="margin-left:12px;font-size:13px;color:#64748b;font-weight:600">Tex-Mex Group</span>
  </div>
  <div class="topbar-right">
    ${critCount > 0 ? `<div class="critical-badge">🔴 ${critCount} CRITICAL OPEN</div>` : ''}
    <div class="scan-note">Last scan: 4 min ago &nbsp;·&nbsp; ${LOCATIONS.length} locations &nbsp;·&nbsp; ${totalEmployees} identities</div>
  </div>
</div>

<div class="main">

  <!-- KPI Strip -->
  <div class="kpi-strip">
    <div class="kpi-card ${level === 'CRITICAL' ? 'critical' : level === 'HIGH' ? 'high' : 'ok'}">
      <div class="kpi-label">Portfolio Risk</div>
      <div class="kpi-val">${avgScore}/100</div>
      <div class="kpi-sub" style="color:${riskColor(level)};font-weight:700">${level}</div>
    </div>
    <div class="kpi-card ${critCount > 0 ? 'critical' : 'ok'}">
      <div class="kpi-label">Open Alerts</div>
      <div class="kpi-val">${totalAlerts}</div>
      <div class="kpi-sub">${critCount} critical</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Identities</div>
      <div class="kpi-val">${totalEmployees}</div>
      <div class="kpi-sub">across ${LOCATIONS.length} locations</div>
    </div>
    <div class="kpi-card ${totalInfostealer > 0 ? 'critical' : 'ok'}">
      <div class="kpi-label">Infostealer Hits</div>
      <div class="kpi-val">${totalInfostealer}</div>
      <div class="kpi-sub">last 30 days</div>
    </div>
    <div class="kpi-card ${totalBreach > 0 ? 'high' : 'ok'}">
      <div class="kpi-label">Breach Alerts</div>
      <div class="kpi-val">${totalBreach}</div>
      <div class="kpi-sub">last 30 days</div>
    </div>
    <div class="kpi-card ${totalSimswap > 0 ? 'critical' : 'ok'}">
      <div class="kpi-label">SIM Swap</div>
      <div class="kpi-val">${totalSimswap}</div>
      <div class="kpi-sub">attempts detected</div>
    </div>
  </div>

  <!-- Location Table + Alerts -->
  <div class="grid-2">
    <div>
      <div class="section-title">Location Portfolio</div>
      <div class="loc-table-wrap">
        <table class="loc-table">
          <thead>
            <tr>
              <th>Location</th>
              <th>Grade</th>
              <th>Risk Score</th>
              <th>Alerts</th>
              <th>Infostealer</th>
              <th>SIM Swap</th>
              <th>Last Incident</th>
            </tr>
          </thead>
          <tbody id="loc-tbody">
            ${LOCATIONS.map(loc => {
              const rc = riskColor(loc.risk);
              const gc = gradeColor(loc.grade);
              return `<tr onclick="showDetail('${loc.id}')" id="row-${loc.id}">
                <td>
                  <div class="loc-name">${loc.name}</div>
                  <div class="loc-city">${loc.city}</div>
                </td>
                <td><div class="grade-chip" style="border-color:${gc};color:${gc}">${loc.grade}</div></td>
                <td><span class="score-pill" style="background:${rc}15;color:${rc};border-color:${rc}40">${loc.risk} ${loc.score}/100</span></td>
                <td>${loc.alerts > 0 ? `<span style="color:${riskColor('CRITICAL')};font-weight:700">${loc.alerts}</span>` : '<span style="color:#22c55e">—</span>'}</td>
                <td>${loc.infostealer > 0 ? `<span style="color:#ef4444;font-weight:600">${loc.infostealer}</span>` : '<span style="color:#64748b">0</span>'}</td>
                <td>${loc.simswap > 0 ? `<span style="color:#ef4444;font-weight:600">${loc.simswap}</span>` : '<span style="color:#64748b">0</span>'}</td>
                <td class="days">${loc.daysSince === 0 ? '<span style="color:#ef4444;font-weight:600">Today</span>' : loc.daysSince < 7 ? `<span style="color:#f97316">${loc.daysSince}d ago</span>` : `${loc.daysSince}d ago`}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div>
      <div class="section-title">Active Alerts</div>
      <div class="alerts-panel">
        <div class="alerts-header">
          <span class="alerts-title">Requires Action</span>
          <span style="font-size:11px;color:#64748b">${ALERTS.length} open</span>
        </div>
        ${ALERTS.map((a, idx) => {
          const rc = riskColor(a.level);
          return `<div class="alert-item">
            <div class="alert-row1">
              <span class="alert-badge" style="background:${rc}20;color:${rc};border-color:${rc}40">${a.level}</span>
              <span class="alert-type">${a.type}</span>
              <span class="alert-ago">${a.ago}</span>
            </div>
            <div class="alert-loc" style="margin-bottom:4px">${a.loc}</div>
            <div class="alert-identity">${a.identity}</div>
            <div class="alert-detail">${a.detail}</div>
            <span class="ack-btn">✓ ACK</span>
            <span class="cw-btn" onclick="openCWTicket(${idx})">↗ CW Ticket</span>
          </div>`;
        }).join("")}
      </div>
    </div>
  </div>

  <!-- Location Detail (shown on row click) -->
  <div class="detail-panel" id="detail-panel">
    <div class="detail-header">
      <div class="detail-name" id="detail-title">—</div>
      <button class="close-btn" onclick="closeDetail()">✕ Close</button>
    </div>
    <div id="detail-body"></div>
  </div>

  <!-- ConnectWise ticket confirmation modal -->
  <div class="cw-modal-overlay" id="cw-modal-overlay">
    <div class="cw-modal">
      <div class="cw-modal-header">
        <span class="cw-modal-check">✓</span>
        <span class="cw-modal-title">ConnectWise Ticket Created</span>
      </div>
      <div class="cw-modal-body" id="cw-modal-body"></div>
      <button class="cw-modal-close" onclick="closeCWModal()">Close</button>
    </div>
  </div>

  <!-- Risk Trend -->
  <div class="trend-section">
    <div class="section-title">Portfolio Risk Trend — 30 Days</div>
    <div class="trend-bars" id="trend-bars"></div>
    <div class="trend-labels" id="trend-labels"></div>
    <div class="portfolio-row">
      <span class="port-label">Portfolio Risk</span>
      <span class="port-score" style="color:${riskColor(level)}">${avgScore}/100</span>
      <span class="port-level" style="background:${riskColor(level)}20;color:${riskColor(level)};border-color:${riskColor(level)}40">${level}</span>
      <span class="port-sub">Avg across ${LOCATIONS.length} locations &nbsp;·&nbsp; Updated 4 min ago</span>
    </div>
  </div>

</div>

<script>
const LOCATIONS = ${JSON.stringify(LOCATIONS)};
const LOCATION_DETAILS = ${JSON.stringify(LOCATION_DETAILS)};
const ALERTS = ${JSON.stringify(ALERTS)};

const CW_BOARDS = {CRITICAL:"Security Incidents",HIGH:"Security Alerts",MEDIUM:"Security Alerts",LOW:"Monitoring"};
const CW_PRIORITY = {CRITICAL:"Priority 1 - Emergency",HIGH:"Priority 2 - High",MEDIUM:"Priority 3 - Medium",LOW:"Priority 4 - Low"};
let cwTicketSeq = 104582;

function buildCWTicket(level, loc, type, identity, summary) {
  cwTicketSeq += 1;
  const ticketId = "CW-" + cwTicketSeq;
  const rc = riskColor(level);
  const body = document.getElementById('cw-modal-body');
  body.innerHTML = \`
    <div class="cw-modal-row"><span class="cw-modal-label">Ticket #</span><span class="cw-modal-val">\${ticketId}</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Board</span><span class="cw-modal-val">\${CW_BOARDS[level] || "Security Alerts"}</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Priority</span><span class="cw-modal-val" style="color:\${rc}">\${CW_PRIORITY[level] || "Priority 3 - Medium"}</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Company</span><span class="cw-modal-val">Tex-Mex Group</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Site</span><span class="cw-modal-val">\${loc}</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Type</span><span class="cw-modal-val">\${type}</span></div>
    <div class="cw-modal-row"><span class="cw-modal-label">Status</span><span class="cw-modal-val" style="color:#22c55e">New</span></div>
    <div class="cw-modal-summary">\${summary}</div>
  \`;
  document.getElementById('cw-modal-overlay').classList.add('visible');
}

function openCWTicket(idx) {
  const a = ALERTS[idx];
  buildCWTicket(a.level, a.loc, a.type, a.identity, \`\${a.identity} — \${a.detail}\`);
}

function openCWTicketForLocation(locId) {
  const loc = LOCATIONS.find(l => l.id === locId);
  buildCWTicket(loc.risk, loc.name, "Multi-Signal Risk Escalation", "", \`Risk score \${loc.score}/100 (\${loc.risk}) — \${loc.alerts} open alert\${loc.alerts === 1 ? '' : 's'} across this location. Ticket opened for remediation follow-up.\`);
}

function closeCWModal() {
  document.getElementById('cw-modal-overlay').classList.remove('visible');
}

function riskColor(l){return l==="CRITICAL"?"#ef4444":l==="HIGH"?"#f97316":l==="MEDIUM"?"#facc15":"#22c55e"}
function gradeColor(g){return g==="A"?"#22c55e":g==="B"?"#4ade80":g==="C"?"#facc15":g==="D"?"#f97316":"#ef4444"}

function showDetail(id) {
  document.querySelectorAll('.loc-table tbody tr').forEach(r => r.classList.remove('selected'));
  const row = document.getElementById('row-'+id);
  if(row) row.classList.add('selected');

  const loc = LOCATIONS.find(l => l.id === id);
  const det = LOCATION_DETAILS[id];
  const panel = document.getElementById('detail-panel');
  const title = document.getElementById('detail-title');
  const body = document.getElementById('detail-body');

  title.innerHTML = \`\${loc.name} &nbsp;<span style="font-size:13px;font-weight:400;color:#64748b">\${loc.city}</span> &nbsp;<span style="font-size:14px;color:\${riskColor(loc.risk)};font-weight:700">\${loc.risk} \${loc.score}/100</span>\`;

  if(!det) {
    body.innerHTML = \`<div style="color:#64748b;font-size:13px;padding:16px 0">No detailed data available for this location in the demo.</div>\`;
    panel.classList.add('visible');
    panel.scrollIntoView({behavior:'smooth',block:'nearest'});
    return;
  }

  const dims = det.dimensions;
  const dimNames = {breach_exposure:'Breach Exposure',infostealer_density:'Infostealer Density',session_exposure:'Session Exposure',cve_exposure:'CVE Exposure',ioc_presence:'IOC Presence',ransomware_victim:'Ransomware Victim'};
  const maxDim = {breach_exposure:25,infostealer_density:25,session_exposure:10,cve_exposure:25,ioc_presence:15,ransomware_victim:20};

  const dimHtml = Object.entries(dims).map(([k,v]) => {
    const pct = Math.min(100,(v/maxDim[k])*100);
    const c = v>=(maxDim[k]*.8)?"#ef4444":v>=(maxDim[k]*.5)?"#f97316":v>0?"#facc15":"#1e3a5f";
    return \`<div class="dim-row"><span class="dim-name">\${dimNames[k]}</span><div class="dim-bar-wrap"><div class="dim-bar" style="width:\${pct}%;background:\${c}"></div></div><span class="dim-val">\${v}</span></div>\`;
  }).join('');

  const idHtml = (det.identities||[]).map(i => {
    const ic = riskColor(i.level);
    return \`<div class="identity-row"><div class="id-top"><span style="background:\${ic}20;color:\${ic};border:1px solid \${ic}40;padding:2px 6px;border-radius:8px;font-size:10px;font-weight:700;flex-shrink:0">\${i.level}</span><span class="id-email">\${i.email}</span><span class="id-score">\${i.score}/100</span></div><div class="id-finding">\${i.finding}</div></div>\`;
  }).join('');

  const tlHtml = (det.timeline||[]).map(t => {
    const tc = riskColor(t.type);
    return \`<div class="timeline-row"><span class="tl-date">\${t.date}</span><div class="tl-dot" style="background:\${tc}"></div><span class="tl-event">\${t.event}</span></div>\`;
  }).join('');

  body.innerHTML = \`
    <div class="detail-grid">
      <div>
        <div class="section-title" style="margin-bottom:10px">Signal Dimensions</div>
        \${dimHtml}
      </div>
      <div>
        <div class="section-title" style="margin-bottom:10px">Monitored Identities</div>
        \${idHtml || '<div style="color:#64748b;font-size:12px">No identity findings</div>'}
      </div>
      <div>
        <div class="section-title" style="margin-bottom:10px">Incident Timeline</div>
        \${tlHtml || '<div style="color:#64748b;font-size:12px">No recent incidents</div>'}
      </div>
    </div>
    <div class="action-bar">
      <button class="action-btn btn-wa" onclick="alert('WhatsApp remediation sent to location manager')">📱 Remediate via WhatsApp</button>
      <button class="action-btn btn-pdf" onclick="alert('PDF risk report generation would open here')">📄 Download Report</button>
      <button class="action-btn btn-cw" onclick="openCWTicketForLocation('\${loc.id}')">↗ Open ConnectWise Ticket</button>
    </div>\`;

  panel.classList.add('visible');
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('visible');
  document.querySelectorAll('.loc-table tbody tr').forEach(r => r.classList.remove('selected'));
}

// Render trend bars
(function(){
  const scores = [28,32,35,30,38,42,40,44,48,42,44,50,46,52,48,44,50,54,52,56,54,58,56,54,58,60,62,58,54,44];
  const labels = ['Jun 1','','','','5','','','','','10','','','','','15','','','','','20','','','','','25','','','','','26'];
  const bars = document.getElementById('trend-bars');
  const lbls = document.getElementById('trend-labels');
  if(!bars) return;
  const maxS = Math.max(...scores);
  scores.forEach((s,i) => {
    const pct = (s/maxS)*100;
    const c = s>=70?"#ef4444":s>=45?"#f97316":s>=22?"#facc15":"#22c55e";
    const b = document.createElement('div');
    b.className='trend-bar';
    b.style.cssText=\`height:\${pct}%;background:\${c};opacity:0.7\`;
    b.title=\`Day \${i+1}: \${s}/100\`;
    bars.appendChild(b);
    const l = document.createElement('div');
    l.className='trend-label';
    l.textContent=labels[i];
    lbls.appendChild(l);
  });
})();
</script>
</body>
</html>`;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const token = url.searchParams.get("token");

    if (token !== DEMO_TOKEN) {
      return new Response(`<!DOCTYPE html>
<html><head><title>RelayShield Multi-Site Shield</title>
<style>body{background:#0a0f1e;color:#e2e8f0;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}</style>
</head><body>
<div>
  <div style="font-size:40px;margin-bottom:16px">🛡</div>
  <div style="font-size:18px;font-weight:700;margin-bottom:8px">RelayShield Multi-Site Shield</div>
  <div style="font-size:14px;color:#4a7fa5">This demo requires an access token.</div>
  <div style="font-size:13px;color:#64748b;margin-top:8px">Contact relayshieldadmin@gmail.com</div>
</div>
</body></html>`, { headers: { "Content-Type": "text/html" }, status: 200 });
    }

    return new Response(renderDashboard(), {
      headers: { "Content-Type": "text/html;charset=UTF-8" },
    });
  }
};
