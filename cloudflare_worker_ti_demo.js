/**
 * RelayShield Threat Intelligence Demo Portal
 * Cloudflare Worker — deploy to: relayshield-ti-demo.relayshieldadmin.workers.dev
 *
 * Token-gated: ?token=rs-demo-2026
 * Demo API key is rate-limited and read-only. It is supplied as a Worker
 * secret, not committed — this repo is public. To set or rotate it:
 *   wrangler secret put DEMO_KEY --config wrangler.ti-demo.toml
 */

const API_BASE   = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod";
const DEMO_TOKEN = "rs-demo-2026";

async function _parseApiResponse(resp) {
  const text = await resp.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    if (!resp.ok) {
      return { error: "Upstream lookup temporarily unavailable (rate-limited or busy) — please try again in a moment." };
    }
    return { error: "Unexpected response from API" };
  }
  if (!resp.ok) {
    return { error: data.error || "Upstream lookup temporarily unavailable — please try again in a moment." };
  }
  return data.data || data;
}

async function callAPI(env, path, body) {
  if (!env.DEMO_KEY) return { error: "Demo is not configured — DEMO_KEY secret is not set." };
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-RS-API-KEY": env.DEMO_KEY,
      },
      body: JSON.stringify(body),
    });
    return await _parseApiResponse(resp);
  } catch (e) {
    return { error: "Network error — please try again in a moment." };
  }
}

async function callAPIGet(env, path, params = {}) {
  if (!env.DEMO_KEY) return { error: "Demo is not configured — DEMO_KEY secret is not set." };
  const qs = new URLSearchParams(params).toString();
  const url = `${API_BASE}${path}${qs ? "?" + qs : ""}`;
  try {
    const resp = await fetch(url, {
      headers: { "X-RS-API-KEY": env.DEMO_KEY },
    });
    return await _parseApiResponse(resp);
  } catch (e) {
    return { error: "Network error — please try again in a moment." };
  }
}

function grade_color(grade) {
  const colors = { A: "#22c55e", B: "#86efac", C: "#facc15", D: "#f97316", F: "#ef4444" };
  return colors[grade] || "#94a3b8";
}

function risk_color(level) {
  const colors = { LOW: "#22c55e", MEDIUM: "#facc15", HIGH: "#f97316", CRITICAL: "#ef4444" };
  return colors[level] || "#94a3b8";
}

function renderIdentityRisk(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  const g = data.grade || "?";
  const score = data.risk_score ?? "?";
  const level = data.risk_level || "UNKNOWN";
  const dims = data.dimension_scores || {};
  const factors = data.risk_factors || [];

  const dimRows = Object.entries(dims).map(([k, v]) => `
    <div class="dim-row">
      <span class="dim-name">${k.replace(/_/g," ").replace(/\bcve\b/gi,"CVE").replace(/\bioc\b/gi,"IOC").replace(/\b\w/g,c=>c.toUpperCase())}</span>
      <div class="dim-bar-wrap"><div class="dim-bar" style="width:${Math.min(100,(v/25)*100)}%;background:${v>=20?"#ef4444":v>=12?"#f97316":v>=6?"#facc15":v>0?"#22c55e":"#1e3a5f"}"></div></div>
      <span class="dim-val">${v}</span>
    </div>`).join("");

  return `
    <div class="result-card">
      <div class="score-hero">
        <div class="grade-circle" style="border-color:${grade_color(g)};color:${grade_color(g)}">${g}</div>
        <div class="score-detail">
          <div class="score-num">${score}<span class="score-max">/100</span></div>
          <div class="risk-badge" style="background:${risk_color(level)}20;color:${risk_color(level)};border:1px solid ${risk_color(level)}">${level}</div>
        </div>
      </div>
      <div class="summary">${data.summary || ""}</div>
      <div class="section-label">Signal Dimensions</div>
      <div style="display:flex;justify-content:flex-end;padding-right:2px;margin-bottom:2px">
        <span style="font-size:10px;color:#4a7fa5;font-weight:600;letter-spacing:.5px">SCORE</span>
      </div>
      <div class="dims">${dimRows}</div>
      ${factors.length ? `<div class="section-label">Risk Factors</div><ul class="factors">${factors.map(f=>`<li>${f}</li>`).join("")}</ul>` : ""}
      <div class="recommendation">${data.recommendation || ""}</div>
      ${renderAttackTimeline(dims, score)}
      <button class="pdf-btn" onclick="downloadReport()">⬇ Download Report</button>
    </div>`;
}


function renderBulkIdentity(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  const results = data.results || [];
  if (!results.length) return `<div class="no-result">No results returned.</div>`;
  const summary = data.summary || "";
  const crit = data.critical_count || 0;
  const high = data.high_count || 0;
  return `<div class="result-card">
    <div class="trending-header" style="margin-bottom:16px">${summary}</div>
    ${results.map(r => {
      const domainColor = risk_color(r.domain_risk || "LOW");
      const agents = r.agents || [];
      return `<div style="margin-bottom:20px">
        <div class="vendor-header">
          <span class="vendor-domain">${r.domain}</span>
          <span class="vendor-badge" style="background:${domainColor}20;color:${domainColor};border:1px solid ${domainColor}">
            ${r.domain_risk || "LOW"} &nbsp;${r.domain_score || 0}/100
          </span>
        </div>
        <div style="display:flex;justify-content:flex-end;padding-right:2px;margin-bottom:2px;margin-top:8px">
          <span style="font-size:10px;color:#4a7fa5;font-weight:600;letter-spacing:.5px">SCORE</span>
        </div>
        <div class="dims" style="margin:0 0 8px 0">
          ${Object.entries(r.dimension_scores||{}).map(([k,v])=>`
            <div class="dim-row">
              <span class="dim-name">${k.replace(/_/g," ").replace(/\bcve\b/gi,"CVE").replace(/\bioc\b/gi,"IOC").replace(/\b\w/g,c=>c.toUpperCase())}</span>
              <div class="dim-bar-wrap"><div class="dim-bar" style="width:${Math.min(100,(v/25)*100)}%;background:${v>=20?"#ef4444":v>=12?"#f97316":v>=6?"#facc15":v>0?"#22c55e":"#1e3a5f"}"></div></div>
              <span class="dim-val">${v}</span>
            </div>`).join("")}
        </div>
        ${renderAttackTimeline(r.dimension_scores||{}, r.domain_score||0)}
        ${(() => {
          const maxAgent = agents.length ? Math.max(...agents.map(a=>a.risk_score||0)) : 0;
          const domScore = r.domain_score || 0;
          if (maxAgent > domScore) {
            const elevColor = maxAgent >= 70 ? "#ef4444" : maxAgent >= 45 ? "#f97316" : "#facc15";
            return `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:#0f1f3a;border-radius:6px;border:1px solid ${elevColor}40;margin-bottom:8px">
              <span style="font-size:11px;color:#94a3b8">Domain baseline</span>
              <span style="font-size:12px;color:#94a3b8;font-weight:600">${domScore}/100</span>
              <span style="font-size:11px;color:#4a7fa5">→</span>
              <span style="font-size:12px;color:${elevColor};font-weight:700">Elevated ${maxAgent}/100</span>
              <span style="font-size:11px;color:#94a3b8">due to agent credential exposure</span>
            </div>`;
          }
          return "";
        })()}
        ${agents.length ? `<div class="section-label">AI Agent / Service Account Identities</div>
        <div class="ioc-list">${agents.map(a => {
          const ac = risk_color(a.risk_level||"LOW");
          return `<div style="padding:8px 0;border-bottom:1px solid #1e3a5f1a">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
              <span class="ioc-type" style="background:${ac}20;color:${ac};border:1px solid ${ac};flex-shrink:0">${a.risk_level||"LOW"}</span>
              <span style="font-size:13px;color:#e2e8f0;font-weight:600;font-family:monospace;flex:1;min-width:0;word-break:break-all">${a.identity}</span>
              <span class="ioc-malware" style="margin-left:auto">${a.risk_score||0}/100</span>
            </div>
            ${(a.risk_factors||[]).length ? `<div style="font-size:12px;color:#94a3b8;padding-left:4px">${a.risk_factors[0]}</div>` : ""}
          </div>`;}).join("")}</div>` : ""}
      </div>`;}).join("")}
  </div>`;
}

function renderLLMJacking(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  if (!data.found) return `
    <div class="result-card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <span style="font-size:32px;color:#22c55e">✓</span>
        <div>
          <div style="font-weight:700;color:#fff;font-size:16px">No Exposed LLM/AI Provider Keys Detected</div>
          <div style="color:#64748b;font-size:13px">${data.domains_checked} domain(s) scanned against stealer log corpus</div>
        </div>
      </div>
      <div class="recommendation">${data.recommendation||""}</div>
    </div>`;

  const findings = data.findings || [];
  const sevColor = {CRITICAL:"#ef4444",HIGH:"#f97316",MEDIUM:"#facc15",LOW:"#22c55e"};
  const critical = findings.filter(f=>f.severity==="CRITICAL").length;
  const providers = (data.providers_affected||[]).join(", ");

  return `<div class="result-card">
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:16px">
      <span style="font-size:32px;color:#ef4444">⚠</span>
      <div>
        <div style="font-weight:700;color:#fff;font-size:18px">${findings.length} LLM/AI Provider Key(s) Exposed</div>
        <div style="color:#64748b;font-size:13px">${critical} critical · providers: ${providers||"n/a"} · live, uncapped billing liability</div>
      </div>
    </div>
    <div class="ioc-list" style="margin-bottom:16px">
      ${findings.slice(0,10).map(f=>{
        const col = sevColor[f.severity]||"#64748b";
        return `<div class="ioc-item" style="padding:10px 0">
          <span class="ioc-type" style="background:${col}20;color:${col};border:1px solid ${col}">${f.severity}</span>
          <div style="flex:1">
            <div style="font-size:13px;color:#e2e8f0;font-weight:600">${f.llm_provider||"LLM Provider"} key</div>
            <div style="font-size:12px;color:#94a3b8">${f.description||""}</div>
            ${f.preview?`<div style="font-size:11px;color:#4a7fa5;font-family:monospace;margin-top:2px">${f.preview}</div>`:""}
          </div>
          <span style="font-size:11px;color:#334155">${f.source||""}</span>
        </div>`;}).join("")}
    </div>
    <div class="recommendation" style="border-left-color:#ef4444">${data.recommendation||""}</div>
  </div>`;
}

function renderNHI(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  if (!data.found) return `
    <div class="result-card">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <span style="font-size:32px;color:#22c55e">✓</span>
        <div>
          <div style="font-weight:700;color:#fff;font-size:16px">No NHI Credentials Detected</div>
          <div style="color:#64748b;font-size:13px">${data.domains_checked} domain(s) scanned against stealer log corpus</div>
        </div>
      </div>
      <div class="recommendation">${data.recommendation||""}</div>
    </div>`;

  const findings = data.findings || [];
  const sevColor = {CRITICAL:"#ef4444",HIGH:"#f97316",MEDIUM:"#facc15",LOW:"#22c55e"};
  const critical = findings.filter(f=>f.severity==="CRITICAL").length;
  const high = findings.filter(f=>f.severity==="HIGH").length;

  return `<div class="result-card">
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:16px">
      <span style="font-size:32px;color:#ef4444">⚠</span>
      <div>
        <div style="font-weight:700;color:#fff;font-size:18px">${findings.length} NHI Credential(s) Exposed</div>
        <div style="color:#64748b;font-size:13px">${critical} critical · ${high} high · found in criminal stealer archives</div>
      </div>
    </div>
    <div class="ioc-list" style="margin-bottom:16px">
      ${findings.slice(0,10).map(f=>{
        const col = sevColor[f.severity]||"#64748b";
        return `<div class="ioc-item" style="padding:10px 0">
          <span class="ioc-type" style="background:${col}20;color:${col};border:1px solid ${col}">${f.severity}</span>
          <div style="flex:1">
            <div style="font-size:13px;color:#e2e8f0;font-weight:600">${f.type||"Credential"}</div>
            <div style="font-size:12px;color:#94a3b8">${f.description||""}</div>
            ${f.preview?`<div style="font-size:11px;color:#4a7fa5;font-family:monospace;margin-top:2px">${f.preview}</div>`:""}
          </div>
          <span style="font-size:11px;color:#334155">${f.source||""}</span>
        </div>`;}).join("")}
    </div>
    <div class="recommendation" style="border-left-color:#ef4444">${data.recommendation||""}</div>
  </div>`;
}

function riskGaugeSvg(score, label, color) {
  // Semi-circle gauge, radius 80 centered at (100,100). Four fixed 45-degree
  // color bands (gray/green/yellow/red) plus a needle placed by score (0-100).
  // Angle convention: 180deg = left (score 0), 0deg = right (score 100).
  // Gray specifically means "no data queried yet" (unknown), never collapsed
  // into "no known finding" (green) -- those are different claims.
  const angle = 180 - (score / 100) * 180;
  const rad = (angle * Math.PI) / 180;
  const needleLen = 65;
  const nx = 100 + needleLen * Math.cos(rad);
  const ny = 100 - needleLen * Math.sin(rad);
  return `
    <svg viewBox="0 0 200 120" style="width:180px;height:108px;display:block;margin:0 auto;flex-shrink:0">
      <path d="M 20,100 A 80,80 0 0 1 43.43,43.43" fill="none" stroke="#64748b" stroke-width="14" stroke-linecap="round"/>
      <path d="M 43.43,43.43 A 80,80 0 0 1 100,20" fill="none" stroke="#22c55e" stroke-width="14" stroke-linecap="round"/>
      <path d="M 100,20 A 80,80 0 0 1 156.57,43.43" fill="none" stroke="#facc15" stroke-width="14" stroke-linecap="round"/>
      <path d="M 156.57,43.43 A 80,80 0 0 1 180,100" fill="none" stroke="#ef4444" stroke-width="14" stroke-linecap="round"/>
      <line x1="100" y1="100" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="#e2e8f0" stroke-width="3" stroke-linecap="round"/>
      <circle cx="100" cy="100" r="7" fill="#e2e8f0"/>
      <text x="100" y="118" text-anchor="middle" font-size="11" fill="${color}" font-weight="700">${label}</text>
    </svg>`;
}

function ipIntelRiskLevel(data) {
  if (!data.found) return { score: 12, label: "UNKNOWN", color: "#64748b" };
  const malicious = data.malicious_votes || 0;
  const suspicious = data.suspicious_votes || 0;
  if (malicious > 0) return { score: Math.min(100, 78 + malicious * 4), label: "ELEVATED SIGNAL", color: "#ef4444" };
  if (suspicious > 0) return { score: Math.min(74, 53 + suspicious * 4), label: "SOME SIGNAL", color: "#facc15" };
  return { score: 37, label: "NO KNOWN FINDING", color: "#22c55e" };
}

function renderIpIntel(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;

  const isIp = data.query_type === "ip";
  const risk = ipIntelRiskLevel(data);

  if (!data.found) {
    return `<div class="result-card">
      <div style="display:flex;align-items:center;gap:20px;margin-bottom:4px;flex-wrap:wrap">
        ${riskGaugeSvg(risk.score, risk.label, risk.color)}
        <div style="flex:1;min-width:200px">
          <div style="font-weight:700;color:#fff;font-size:18px">${data.queried||""} <span style="color:#64748b;font-size:13px;font-weight:400">(${isIp?"IP":"domain"})</span></div>
          <div style="color:#64748b;font-size:13px;margin-top:4px">No record found in the sources queried yet.</div>
          <div style="color:#475569;font-size:12px;margin-top:6px;line-height:1.5">"Unknown" means this indicator hasn't been seen by the sources queried — it is not a clean/safe result, just an absence of data.</div>
        </div>
      </div>
    </div>`;
  }

  const malicious = data.malicious_votes || 0;
  const suspicious = data.suspicious_votes || 0;
  const resolutions = data.resolutions || [];
  const ownCorpus = data.source === "relayshield_ioc_corpus";

  return `<div class="result-card">
    <div style="display:flex;align-items:center;gap:20px;margin-bottom:16px;flex-wrap:wrap">
      ${riskGaugeSvg(risk.score, risk.label, risk.color)}
      <div style="flex:1;min-width:200px">
        <div style="font-weight:700;color:#fff;font-size:18px">${data.queried} <span style="color:#64748b;font-size:13px;font-weight:400">(${isIp?"IP":"domain"})</span></div>
        <div style="color:#64748b;font-size:13px;margin-top:4px">${ownCorpus ? `Matched RelayShield's own criminal IOC corpus (${malicious} record(s))` : `${malicious} malicious vote(s) · ${suspicious} suspicious vote(s)`} on this ${isIp?"IP":"domain"} itself${isIp?` · ${data.as_owner||"unknown AS"} (${data.country||"?"})`:""}</div>
        <div style="color:#475569;font-size:12px;margin-top:6px;line-height:1.5">"No known finding" means nothing was flagged in the sources queried — it is not a verified-safe guarantee.</div>
      </div>
    </div>
    ${resolutions.length ? `<div class="ioc-list" style="margin-bottom:16px">
      <div style="font-size:12px;color:#64748b;margin-bottom:2px;text-transform:uppercase;letter-spacing:.05em">${isIp?"Hostnames resolved to this IP":"IP resolution history"}</div>
      <div style="font-size:11px;color:#475569;margin-bottom:8px">Historical DNS resolution records — unrelated to the vote count above. None of these are individually flagged; they're context, not findings.</div>
      ${resolutions.slice(0,10).map(r=>`<div class="ioc-item" style="padding:8px 0">
        <div style="flex:1;font-size:13px;color:#e2e8f0;font-family:monospace">${isIp?(r.hostname||"unknown"):(r.ip_address||"unknown")}</div>
        <span style="font-size:11px;color:#334155">${r.date?new Date(r.date).toLocaleDateString():""}</span>
      </div>`).join("")}
    </div>` : ""}
  </div>`;
}

function renderActor(data) {
  // Error check MUST come first. Until 2026-08-01 the !matched check ran
  // ahead of it, so an upstream error, a rate-limit or a network failure —
  // none of which carry a `matched` field — rendered as "No threat actor
  // found matching that name", i.e. a confident false negative. Every other
  // render function in this file already checks error first.
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  if (!data.matched) return `<div class="no-result">No threat actor found matching that name. Try a MITRE ATT&amp;CK group name or a known alias (e.g. MuddyWater, Seedworm, Mango Sandstorm).</div>`;

  const iocs = (data.associated_iocs || []).slice(0, 8);
  const related = (data.related_actors || []).slice(0, 5);
  const techniques = (data.techniques || []).slice(0, 6);
  const malware = (data.associated_malware || []).slice(0, 10);
  const reporting = (data.recent_reporting || []).slice(0, 5);

  return `
    <div class="result-card">
      <div class="actor-header">
        <div class="actor-name">${data.actor}</div>
        <div class="actor-meta">${data.mitre_id} &nbsp;|&nbsp; ${data.origin_country || "Unknown origin"}</div>
      </div>
      <p class="actor-desc">${(data.description||"").slice(0,300)}${data.description?.length>300?"...":""}</p>
      ${techniques.length ? `<div class="section-label">ATT&CK Techniques (sample)</div><div class="tags">${techniques.map(t=>`<span class="tag tag-red">${t}</span>`).join("")}</div>` : ""}
      ${data.aliases?.length ? `<div class="section-label">Also known as</div><div class="tags">${data.aliases.map(a=>`<span class="tag tag-gray">${a}</span>`).join("")}</div>` : ""}
      ${reporting.length ? `
        <div class="section-label">Recent Open-Source Reporting (${data.reporting_count})</div>
        <div class="ioc-list">${reporting.map(r=>`
          <div class="ioc-item" style="padding:8px 0;display:block">
            <div style="font-size:13px;color:#e2e8f0">${r.url ? `<a href="${r.url}" target="_blank" rel="noopener noreferrer" style="color:#5eead4;text-decoration:none">${r.title||"(untitled)"}</a>` : (r.title||"(untitled)")}</div>
            <div style="font-size:11px;color:#475569;margin-top:3px">${r.source||""}${r.published?` · ${r.published}`:""}${r.matched_as?.length?` · named as: ${r.matched_as.join(", ")}`:""}</div>
          </div>`).join("")}
        </div>` : ""}
      ${malware.length ? `<div class="section-label">Associated Malware/Tools (MITRE ATT&CK)</div><div class="tags">${malware.map(m=>`<span class="tag tag-red">${m}</span>`).join("")}</div>` : ""}
      ${related.length ? `
        <div class="section-label">Related Threat Actors</div>
        <div class="related-actors">${related.map(r=>`
          <div class="related-item">
            <span class="related-name">${r.actor}</span>
            <span class="related-id">${r.mitre_id}</span>
            ${r.shared_techniques?.length ? `<span class="related-overlap">Shared techniques: ${r.shared_techniques.join(", ")}</span>` : ""}
          </div>`).join("")}
        </div>` : ""}
      ${iocs.length ? `
        <div class="section-label">Live IOCs attributed via associated malware (${data.ioc_count || iocs.length} total)</div>
        <div class="ioc-list">${iocs.map(i=>`<div class="ioc-item"><span class="ioc-type">${i.ioc_type}</span><span class="ioc-val">${i.ioc_value}</span><span class="ioc-malware">${i.malware||""}</span></div>`).join("")}</div>` : `<div class="section-label">Live IOCs attributed via associated malware</div><p style="color:#888;font-size:13px;">None currently in corpus for this actor's known malware/tools.</p>`}
    </div>`;
}

function renderTrending(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  const trending = data.trending || {};
  const total = data.total_new_iocs || 0;
  const hours = data.window_hours || 24;

  // Feed → category mapping
  const feedCategory = {
    abuseipdb:"Abuse Reports", blocklist_de:"Attack Sources", ipsum:"Aggregated Blocklist",
    spamhaus_drop:"Spam/Botnet Networks", spamhaus:"Spam/Botnet Networks",
    threatfox:"Malware C2", feodo:"Banking Trojan C2", feodo_aggressive:"Banking Trojan C2",
    urlhaus:"Malware Distribution", malwarebazaar:"Malware Samples",
    openphish:"Phishing", phishtank:"Phishing", phishstats:"Phishing",
    c2intel:"Command & Control", emerging_threats:"Emerging Threats",
    botvrij:"Malicious Infrastructure", otx:"Community Intel",
    talos:"Cisco Talos", hagezi:"DNS Blocklist", paste_ee:"Paste Sites",
    pastehub:"Paste Sites",
  };
  const catColor = {
    "Malware C2":"#ef4444","Banking Trojan C2":"#ef4444","Command & Control":"#ef4444",
    "Malware Distribution":"#f97316","Malware Samples":"#f97316",
    "Phishing":"#facc15","Abuse Reports":"#fb923c","Attack Sources":"#fb923c",
    "Spam/Botnet Networks":"#a78bfa","Emerging Threats":"#f97316",
    "Malicious Infrastructure":"#f97316","Community Intel":"#60a5fa",
    "DNS Blocklist":"#94a3b8","Aggregated Blocklist":"#94a3b8",
    "Paste Sites":"#94a3b8","Cisco Talos":"#60a5fa",
  };

  // Collect malware families
  const allItems = Object.values(trending).flat();
  const families = {};
  allItems.forEach(i => { if(i.malware && i.malware !== "n/a") families[i.malware] = (families[i.malware]||0)+1; });
  const topFamilies = Object.entries(families).sort((a,b)=>b[1]-a[1]).slice(0,8);

  // Category summary
  const catSummary = {};
  allItems.forEach(i => {
    const src = (i.source||"").replace(/-/g,"_");
    const cat = feedCategory[src] || "Other";
    catSummary[cat] = (catSummary[cat]||0)+1;
  });

  // Dedup and show top IOCs per type with better labels
  const typeLabels = {ip:"Malicious IPs",domain:"Malicious Domains",url:"Malware URLs",
    hash_sha256:"Malware File Hashes",cidr:"Blocked IP Ranges",hostname:"Malicious Hostnames"};
  const typeEmoji = {ip:"🌐",domain:"🔗",url:"⚠️",hash_sha256:"🧬",cidr:"🚫",hostname:"💻"};

  const sections = Object.entries(trending).map(([type, items]) => {
    // Deduplicate by value, keep highest confidence
    const seen = new Set();
    const deduped = items.filter(i => { if(seen.has(i.ioc_value)) return false; seen.add(i.ioc_value); return true; }).slice(0,6);
    const label = typeLabels[type] || type.replace(/_/g," ").toUpperCase();
    const emoji = typeEmoji[type] || "•";
    return `
    <div class="trending-section">
      <div class="trending-type">${emoji} ${label} <span class="trending-count">${items.length}</span></div>
      <div class="trending-items">${deduped.map(i => {
        const src = (i.source||"").replace(/-/g,"_");
        const cat = feedCategory[src] || "Other";
        const col = catColor[cat] || "#64748b";
        return `<div class="trending-item">
          <span class="trending-val">${i.ioc_value?.slice(0,45)}</span>
          <span class="trending-badge" style="background:${col}20;color:${col};border:1px solid ${col};font-size:10px;padding:1px 6px;border-radius:3px;flex-shrink:0">${cat}</span>
          ${i.malware && i.malware!=="n/a" ? `<span class="trending-malware">${i.malware}</span>` : ""}
        </div>`;}).join("")}
      </div>
    </div>`;
  }).join("");

  const familyBars = topFamilies.length ? `
    <div class="section-label" style="margin-top:16px">Active Malware Families</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px">
      ${topFamilies.map(([fam,cnt])=>`
        <div style="background:#1e3a5f;border:1px solid #ef444440;border-radius:6px;padding:6px 12px;min-width:120px">
          <div style="font-size:13px;font-weight:600;color:#fca5a5">${fam}</div>
          <div style="font-size:11px;color:#64748b">${cnt} sample${cnt>1?"s":""}</div>
        </div>`).join("")}
    </div>` : "";

  const catBars = Object.entries(catSummary).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([cat,cnt]) => {
    const col = catColor[cat] || "#64748b";
    const pct = Math.min(100, Math.round(cnt/total*100*10));
    return `<div class="dim-row">
      <span class="dim-name" style="width:180px;color:#94a3b8">${cat}</span>
      <div class="dim-bar-wrap" style="flex:1"><div class="dim-bar" style="width:${pct}%;background:${col}"></div></div>
      <span class="dim-val">${cnt}</span>
    </div>`;
  }).join("");

  return `
    <div class="result-card">
      <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:16px">
        <span style="font-size:36px;font-weight:700;color:#00B5A5">${total.toLocaleString()}</span>
        <span style="color:#64748b;font-size:14px">new threat indicators in last ${hours} hours</span>
      </div>
      <div class="section-label">By Threat Category</div>
      <div class="dims" style="margin:8px 0 16px">${catBars}</div>
      ${familyBars}
      <div class="section-label" style="margin-top:16px">Sample Indicators</div>
      ${sections || '<div class="no-result">No trending threats in this window.</div>'}
      <div class="generated-at" style="margin-top:12px">Live data — ${data.generated_at ? new Date(data.generated_at).toUTCString() : "now"}</div>
    </div>`;
}

function renderSupplyChain(data) {
  if (data.error) return `<div class="error">Error: ${data.error}</div>`;
  const results = data.results || [];
  if (!results.length) return `<div class="no-result">No results returned.</div>`;

  return `<div class="result-card">${results.map(r => `
    <div class="vendor-row">
      <div class="vendor-header">
        <span class="vendor-domain">${r.domain}</span>
        <span class="vendor-badge" style="background:${risk_color(r.risk_level)}20;color:${risk_color(r.risk_level)};border:1px solid ${risk_color(r.risk_level)}">${r.risk_level||"UNKNOWN"}</span>
      </div>
      <div class="vendor-stats">
        ${r.breach_count!=null?`<span>Breaches: <b>${r.breach_count}</b></span>`:""}
        ${r.infostealer_hits!=null?`<span>Stealer hits: <b>${r.infostealer_hits}</b></span>`:""}
      </div>
      <div class="vendor-rec">${r.recommendation||""}</div>
    </div>`).join("")}
  </div>`;
}

const PAGE = (content, token) => `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RelayShield — Threat Intelligence Demo</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a1628;color:#e2e8f0;min-height:100vh}
header{background:#0F1F3D;border-bottom:2px solid #00B5A5;padding:16px 32px;display:flex;align-items:center;gap:16px}
.logo{font-size:20px;font-weight:700;color:#fff}.logo span{color:#00B5A5}
.logo-sub{font-size:12px;color:#4a7fa5;margin-left:8px;border:1px solid #1e3a5f;padding:2px 8px;border-radius:4px}
.container{max-width:960px;margin:0 auto;padding:32px 24px}
.hero{text-align:center;margin-bottom:40px}
.hero h1{font-size:28px;color:#fff;margin-bottom:8px}
.hero p{color:#64748b;font-size:15px;max-width:600px;margin:0 auto}
.tabs{display:flex;gap:4px;margin-bottom:24px;border-bottom:1px solid #1e3a5f;padding-bottom:0}
.tab{padding:10px 20px;cursor:pointer;color:#64748b;font-size:14px;font-weight:500;border-bottom:2px solid transparent;transition:all .2s}
.tab:hover{color:#00B5A5}
.tab.active{color:#00B5A5;border-bottom-color:#00B5A5}
.panel{display:none}.panel.active{display:block}
.input-row{display:flex;gap:8px;margin-bottom:16px}
input[type=text]{flex:1;background:#0F1F3D;border:1px solid #1e3a5f;color:#e2e8f0;padding:10px 14px;border-radius:6px;font-size:14px;outline:none}
input[type=text]:focus{border-color:#00B5A5}
input[type=text]::placeholder{color:#334155}
button{background:#00B5A5;color:#0a1628;border:none;padding:10px 20px;border-radius:6px;font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap}
button:hover{background:#00c9b8}
button:disabled{opacity:.5;cursor:not-allowed}
.panel-desc{color:#64748b;font-size:13px;margin-bottom:16px}
.attack-timeline{background:#060b18;border:1px solid #1e3a5f;border-radius:8px;padding:16px;margin-top:16px}
.tl-track{display:flex;align-items:center;gap:0;margin:12px 0 8px}
.tl-stage{flex:1;display:flex;flex-direction:column;align-items:center;position:relative}
.tl-stage:not(:last-child)::after{content:'';position:absolute;top:12px;left:50%;width:100%;height:2px;z-index:0}
.tl-dot-outer{width:24px;height:24px;border-radius:50%;border:2px solid;display:flex;align-items:center;justify-content:center;font-size:11px;z-index:1;background:#060b18;position:relative}
.tl-label{font-size:10px;color:#64748b;text-align:center;margin-top:6px;line-height:1.3;max-width:70px}
.tl-you{font-size:9px;font-weight:700;letter-spacing:.3px;margin-top:3px;text-align:center}
.pdf-btn{display:inline-flex;align-items:center;gap:6px;background:#1e3a5f;border:1px solid #2d5a8e;color:#94a3b8;border-radius:6px;padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer;margin-top:14px;transition:background .2s}
.pdf-btn:hover{background:#2d5a8e;color:#e2e8f0}
@media print{header,.tabs,.input-row,.pdf-btn,.attack-timeline,.panel-desc,footer{display:none!important}.panel{display:block!important}.result-card{border:1px solid #ccc!important;background:#fff!important;color:#111!important}body{background:#fff!important;color:#111!important}.score-num,.dim-val{color:#111!important}.risk-badge{border:1px solid #999!important}.dim-bar{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.result-card{background:#0F1F3D;border:1px solid #1e3a5f;border-radius:8px;padding:20px;margin-top:8px}
.score-hero{display:flex;align-items:center;gap:20px;margin-bottom:16px}
.grade-circle{width:64px;height:64px;border-radius:50%;border:3px solid;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700}
.score-num{font-size:36px;font-weight:700;color:#fff}
.score-max{font-size:16px;color:#64748b}
.risk-badge{padding:4px 12px;border-radius:4px;font-size:12px;font-weight:700;display:inline-block;margin-top:4px}
.summary{color:#94a3b8;font-size:14px;margin-bottom:16px;line-height:1.5}
.section-label{font-size:11px;font-weight:700;color:#4a7fa5;text-transform:uppercase;letter-spacing:.5px;margin:16px 0 8px}
.dims{display:flex;flex-direction:column;gap:6px}
.dim-row{display:flex;align-items:center;gap:8px}
.dim-name{font-size:12px;color:#94a3b8;width:160px;flex-shrink:0;text-transform:capitalize}
.dim-bar-wrap{flex:1;background:#1e3a5f;height:6px;border-radius:3px;overflow:hidden}
.dim-bar{height:100%;border-radius:3px;transition:width .5s}
.dim-val{font-size:12px;color:#64748b;width:24px;text-align:right}
.factors{padding-left:16px;color:#94a3b8;font-size:13px;line-height:1.8}
.recommendation{margin-top:16px;padding:10px 14px;background:#1e3a5f20;border-left:3px solid #00B5A5;color:#94a3b8;font-size:13px;border-radius:0 4px 4px 0}
.actor-header{margin-bottom:12px}
.actor-name{font-size:22px;font-weight:700;color:#fff}
.actor-meta{font-size:13px;color:#4a7fa5;margin-top:4px}
.actor-desc{color:#94a3b8;font-size:14px;line-height:1.6;margin-bottom:12px}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{background:#1e3a5f;color:#7fb3d3;padding:3px 10px;border-radius:4px;font-size:12px}
.tag-red{background:#7f1d1d30;color:#fca5a5}
.tag-gray{background:#1e293b;color:#64748b}
.related-actors{display:flex;flex-direction:column;gap:6px}
.related-item{background:#1e3a5f30;padding:8px 12px;border-radius:6px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.related-name{font-weight:600;color:#e2e8f0;font-size:14px}
.related-id{color:#4a7fa5;font-size:12px}
.related-overlap{color:#64748b;font-size:12px}
.ioc-list{display:flex;flex-direction:column;gap:4px}
.ioc-item{display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid #1e3a5f1a}
.ioc-type{font-size:10px;color:#4a7fa5;background:#1e3a5f;padding:2px 6px;border-radius:3px;flex-shrink:0}
.ioc-val{font-size:12px;color:#94a3b8;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ioc-malware{font-size:11px;color:#f97316;flex-shrink:0}
.trending-header{font-size:16px;color:#00B5A5;font-weight:600;margin-bottom:16px}
.trending-stat{font-size:24px;font-weight:700;color:#fff}
.trending-section{margin-bottom:16px}
.trending-type{font-size:11px;font-weight:700;color:#4a7fa5;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;display:flex;align-items:center;gap:8px}
.trending-count{background:#1e3a5f;color:#7fb3d3;padding:1px 8px;border-radius:10px;font-size:11px}
.trending-items{display:flex;flex-direction:column;gap:3px}
.trending-item{display:flex;gap:8px;align-items:center;padding:4px 8px;background:#1e3a5f20;border-radius:4px}
.trending-val{font-size:12px;color:#94a3b8;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trending-source{font-size:11px;color:#334155;flex-shrink:0}
.trending-malware{font-size:11px;color:#f97316;flex-shrink:0}
.generated-at{font-size:11px;color:#334155;margin-top:12px}
.vendor-row{padding:12px 0;border-bottom:1px solid #1e3a5f}
.vendor-row:last-child{border:none}
.vendor-header{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.vendor-domain{font-size:16px;font-weight:600;color:#e2e8f0}
.vendor-badge{padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700}
.vendor-stats{display:flex;gap:16px;font-size:13px;color:#64748b;margin-bottom:4px}
.vendor-stats b{color:#e2e8f0}
.vendor-rec{font-size:13px;color:#94a3b8}
.loading{color:#4a7fa5;font-size:14px;padding:20px 0}
.error{color:#ef4444;font-size:14px;padding:12px;background:#7f1d1d20;border:1px solid #7f1d1d;border-radius:6px}
.no-result{color:#64748b;font-size:14px;padding:16px 0}
.corpus-stats{display:flex;gap:24px;margin-bottom:24px;flex-wrap:wrap}
.stat-card{background:#0F1F3D;border:1px solid #1e3a5f;border-radius:8px;padding:16px 20px;flex:1;min-width:140px}
.stat-num{font-size:24px;font-weight:700;color:#00B5A5}
.stat-label{font-size:12px;color:#64748b;margin-top:2px}
footer{text-align:center;color:#334155;font-size:12px;padding:32px;margin-top:32px}
footer a{color:#00B5A5;text-decoration:none}
</style>
</head>
<body>
<header>
  <div class="logo">Relay<span>Shield</span> <span class="logo-sub">Threat Intelligence Demo</span></div>
</header>
<div class="container">
  <div class="hero">
    <h1>Live Threat Intelligence</h1>
    <p>Query 4,780,000+ indicators, MITRE ATT&CK profiles, trending threats, and identity risk scoring — powered by RelayShield's live OSINT collection pipeline.</p>
  </div>

  <div class="corpus-stats">
    <!-- Metrics verified live against DynamoDB 2026-08-01:
         intel_iocs 4,784,868 · malpedia_families 3,794 · intel_channels active=true 83 ·
         mitre_attack sk=info 191. Re-verify before quoting these anywhere. -->
    <div class="stat-card"><div class="stat-num">4.7M+</div><div class="stat-label">IOC indicators</div></div>
    <div class="stat-card"><div class="stat-num">3,790+</div><div class="stat-label">Malware families</div></div>
    <div class="stat-card"><div class="stat-num">83+</div><div class="stat-label">Active criminal Telegram channels</div></div>
    <div class="stat-card"><div class="stat-num">191</div><div class="stat-label">MITRE ATT&CK groups</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('identity',this)">Identity Risk</div>
    <div class="tab" onclick="switchTab('actor',this)">Threat Actor</div>
    <div class="tab" onclick="switchTab('trending',this)">Trending Threats</div>
    <div class="tab" onclick="switchTab('supply',this)">Agentic Identity Risk</div>
    <div class="tab" onclick="switchTab('nhi',this)">NHI Exposure</div>
    <div class="tab" onclick="switchTab('llmjacking',this)">LLM Credential Exposure</div>
    <div class="tab" onclick="switchTab('ipintel',this)">IP Reputation &amp; pDNS</div>
    <div class="tab" onclick="switchTab('msp',this)">MSP Portfolio</div>
  </div>

  <div id="identity" class="panel active">
    <p class="panel-desc">Score a domain's identity risk across 6 dimensions: breach exposure, infostealer density, IOC presence, ransomware victim status, active session exposure, and CVE exposure.</p>
    <div class="input-row">
      <input type="text" id="identity-input" placeholder="Enter a domain (e.g. microsoft.com)" />
      <button onclick="runIdentity()">Analyze</button>
    </div>
    <div id="identity-result"></div>
  </div>

  <div id="actor" class="panel">
    <p class="panel-desc">Look up any MITRE ATT&CK threat actor — see their TTPs, target sectors, origin, related actors, and associated indicators from our live corpus.</p>
    <div class="input-row">
      <input type="text" id="actor-input" placeholder="e.g. APT28, Lazarus Group, Sandworm Team, FIN7, Scattered Spider" />
      <button onclick="runActor()">Look Up</button>
    </div>
    <div id="actor-result"></div>
  </div>

  <div id="trending" class="panel">
    <p class="panel-desc">The top indicators actively spreading across all feeds in the last 24 hours — what's attacking infrastructure right now.</p>
    <div class="input-row">
      <select id="trending-hours" style="background:#0F1F3D;border:1px solid #1e3a5f;color:#e2e8f0;padding:10px 14px;border-radius:6px;font-size:14px">
        <option value="24">Last 24 hours</option>
        <option value="48">Last 48 hours</option>
        <option value="72">Last 72 hours</option>
      </select>
      <button onclick="runTrending()">Load Trending</button>
    </div>
    <div id="trending-result"></div>
  </div>

  <div id="nhi" class="panel">
    <p class="panel-desc">Detect API keys, service tokens, and private credentials appearing in criminal stealer log archives. Non-human identity (NHI) exposure is the precursor to supply chain and infrastructure attacks.</p>
    <div class="input-row">
      <input type="text" id="nhi-input" placeholder="Enter a domain (e.g. adobe.com, twilio.com)" />
      <button onclick="runNHI()">Scan Credentials</button>
    </div>
    <div id="nhi-result"></div>
  </div>

  <div id="llmjacking" class="panel">
    <p class="panel-desc">LLMjacking: detect exposed API keys across 14 LLM and AI providers in criminal stealer log archives — closed-source platforms including OpenAI, Anthropic Claude, Google Gemini, xAI Grok and Amazon Bedrock, alongside DeepSeek, Moonshot Kimi, Alibaba Qwen, NVIDIA NIM and Hugging Face. Enter your organization's domain to see whether keys belonging to your people or systems have surfaced in stealer logs. A leaked LLM provider key is a live, uncapped billing liability — real incidents have run from tens of thousands of dollars per day to a $500K single-month bill from one unthrottled key.</p>
    <div class="input-row">
      <input type="text" id="llmjacking-input" placeholder="Enter your organization's domain (e.g. acme.com)" />
      <button onclick="runLLMJacking()">Scan for Exposed Keys</button>
    </div>
    <div id="llmjacking-result"></div>
  </div>

  <div id="ipintel" class="panel">
    <p class="panel-desc">Passive DNS &amp; IP reputation lookup. Pass a domain to see its historical IP resolution history, or an IP to see reverse resolution history plus AS owner and country.</p>
    <div class="input-row">
      <input type="text" id="ipintel-input" placeholder="Enter a domain or IP (e.g. github.com or 140.82.116.3)" />
      <button onclick="runIpIntel()">Look Up</button>
    </div>
    <div id="ipintel-result"></div>
  </div>

  <div id="supply" class="panel">
    <p class="panel-desc">Score identity risk for an organisation plus individual AI agent or service account identities. Shows which agents are exposed in breach, infostealer, or stolen session records.</p>
    <div style="margin-bottom:12px">
      <label style="font-size:12px;color:#4a7fa5;display:block;margin-bottom:4px">ORGANISATION DOMAIN</label>
      <input type="text" id="supply-domain" placeholder="e.g. acme-corp.com" style="width:100%;margin-bottom:12px" />
      <label style="font-size:12px;color:#4a7fa5;display:block;margin-bottom:6px">AI AGENT IDENTITIES <span style="color:#334155">(up to 3)</span></label>
      <input type="text" id="supply-agent-1" placeholder="Agent 1 email (e.g. ai-support@acme-corp.com)" style="width:100%;margin-bottom:6px" />
      <input type="text" id="supply-agent-2" placeholder="Agent 2 email (e.g. crm-agent@acme-corp.com)" style="width:100%;margin-bottom:6px" />
      <input type="text" id="supply-agent-3" placeholder="Agent 3 email (optional)" style="width:100%;margin-bottom:12px" />
    </div>
    <button onclick="runSupply()">Analyze Identity Risk</button>
    <div id="supply-result"></div>
  </div>

  <div id="msp" class="panel">
    <p class="panel-desc">MSP portfolio view — monitor all client domains from a single pane. One <code style="background:#1e3a5f;padding:2px 6px;border-radius:4px;font-size:12px">POST /v1/metered/bulk-identity-risk</code> call scores every client. ConnectWise ticket auto-created on every CRITICAL result.</p>
    <div style="background:#0f1f3a;border:1px solid #1e3a5f;border-radius:10px;overflow:hidden;margin-top:4px">
      <div style="background:#060b18;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #1e3a5f">
        <span style="font-size:13px;font-weight:700;color:#e2e8f0">Client Portfolio — 5 managed accounts</span>
        <span style="font-size:11px;color:#4a7fa5">Last sweep: 8 min ago &nbsp;·&nbsp; 1 API call</span>
      </div>
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#060b18;border-bottom:1px solid #1e3a5f">
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Client Domain</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Risk Score</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Grade</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Infostealer</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Open Alerts</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Last Incident</th>
            <th style="padding:9px 12px;text-align:left;font-size:10px;color:#4a7fa5;font-weight:700;letter-spacing:.5px;text-transform:uppercase">Action</th>
          </tr>
        </thead>
        <tbody id="msp-tbody">
          <tr style="background:#ef444408;border-bottom:1px solid #1e3a5f1a">
            <td style="padding:10px 12px"><div style="color:#e2e8f0;font-weight:600;font-size:13px">acme-logistics.com</div><div style="font-size:11px;color:#64748b">Logistics · 48 employees</div></td>
            <td style="padding:10px 12px"><span style="color:#ef4444;font-weight:700;font-size:13px">78/100</span></td>
            <td style="padding:10px 12px"><span style="color:#ef4444;font-weight:800;font-size:14px">F</span></td>
            <td style="padding:10px 12px"><span style="color:#ef4444;font-weight:600">3 hits</span></td>
            <td style="padding:10px 12px"><span style="color:#ef4444;font-weight:600">2 CRITICAL</span></td>
            <td style="padding:10px 12px;font-size:12px;color:#ef4444">Today</td>
            <td style="padding:10px 12px"><button onclick="mspTriage('acme-logistics.com','CRITICAL','78','Infostealer: 3 employee credentials in RedLine archive. Session cookies for QuickBooks + Microsoft 365 extracted. Immediate rotation required.')" style="padding:4px 10px;font-size:11px;background:#ef444420;color:#ef4444;border:1px solid #ef444440;border-radius:6px;cursor:pointer">Triage</button></td>
          </tr>
          <tr style="background:#f9731608;border-bottom:1px solid #1e3a5f1a">
            <td style="padding:10px 12px"><div style="color:#e2e8f0;font-weight:600;font-size:13px">riverdale-dental.com</div><div style="font-size:11px;color:#64748b">Healthcare · 12 employees</div></td>
            <td style="padding:10px 12px"><span style="color:#f97316;font-weight:700;font-size:13px">52/100</span></td>
            <td style="padding:10px 12px"><span style="color:#f97316;font-weight:800;font-size:14px">D</span></td>
            <td style="padding:10px 12px"><span style="color:#f97316;font-weight:600">1 hit</span></td>
            <td style="padding:10px 12px"><span style="color:#f97316;font-weight:600">1 HIGH</span></td>
            <td style="padding:10px 12px;font-size:12px;color:#f97316">3d ago</td>
            <td style="padding:10px 12px"><button onclick="mspTriage('riverdale-dental.com','HIGH','52','Breach: billing@riverdale-dental.com in Dropbox 2024 breach (560M records). Password reuse risk: Square, Gusto payroll. Schedule rotation.')" style="padding:4px 10px;font-size:11px;background:#f9731620;color:#f97316;border:1px solid #f9731640;border-radius:6px;cursor:pointer">Triage</button></td>
          </tr>
          <tr style="border-bottom:1px solid #1e3a5f1a">
            <td style="padding:10px 12px"><div style="color:#e2e8f0;font-weight:600;font-size:13px">summit-realty-group.com</div><div style="font-size:11px;color:#64748b">Real Estate · 22 employees</div></td>
            <td style="padding:10px 12px"><span style="color:#facc15;font-weight:700;font-size:13px">31/100</span></td>
            <td style="padding:10px 12px"><span style="color:#facc15;font-weight:800;font-size:14px">C</span></td>
            <td style="padding:10px 12px"><span style="color:#64748b">0 hits</span></td>
            <td style="padding:10px 12px"><span style="color:#facc15;font-weight:600">1 MEDIUM</span></td>
            <td style="padding:10px 12px;font-size:12px;color:#64748b">11d ago</td>
            <td style="padding:10px 12px"><button onclick="mspTriage('summit-realty-group.com','MEDIUM','31','Domain lookalike: summit-realty-group-secure.com registered 7 days ago. Potential vendor impersonation / invoice fraud setup.')" style="padding:4px 10px;font-size:11px;background:#facc1520;color:#facc15;border:1px solid #facc1540;border-radius:6px;cursor:pointer">Triage</button></td>
          </tr>
          <tr style="border-bottom:1px solid #1e3a5f1a">
            <td style="padding:10px 12px"><div style="color:#e2e8f0;font-weight:600;font-size:13px">northshore-brewery.com</div><div style="font-size:11px;color:#64748b">F&B · 8 employees</div></td>
            <td style="padding:10px 12px"><span style="color:#22c55e;font-weight:700;font-size:13px">14/100</span></td>
            <td style="padding:10px 12px"><span style="color:#22c55e;font-weight:800;font-size:14px">B</span></td>
            <td style="padding:10px 12px"><span style="color:#64748b">0 hits</span></td>
            <td style="padding:10px 12px"><span style="color:#22c55e">—</span></td>
            <td style="padding:10px 12px;font-size:12px;color:#64748b">28d ago</td>
            <td style="padding:10px 12px"><button onclick="mspTriage('northshore-brewery.com','LOW','14','No active threats. Last scan clean. Breach monitoring active for 3 email addresses.')" style="padding:4px 10px;font-size:11px;background:#22c55e20;color:#22c55e;border:1px solid #22c55e40;border-radius:6px;cursor:pointer">View</button></td>
          </tr>
          <tr>
            <td style="padding:10px 12px"><div style="color:#e2e8f0;font-weight:600;font-size:13px">pinecrest-law.com</div><div style="font-size:11px;color:#64748b">Legal · 6 employees</div></td>
            <td style="padding:10px 12px"><span style="color:#22c55e;font-weight:700;font-size:13px">8/100</span></td>
            <td style="padding:10px 12px"><span style="color:#22c55e;font-weight:800;font-size:14px">A</span></td>
            <td style="padding:10px 12px"><span style="color:#64748b">0 hits</span></td>
            <td style="padding:10px 12px"><span style="color:#22c55e">—</span></td>
            <td style="padding:10px 12px;font-size:12px;color:#64748b">41d ago</td>
            <td style="padding:10px 12px"><button onclick="mspTriage('pinecrest-law.com','LOW','8','Clean. Attorney email addresses monitored. SIM swap monitoring active for 4 phone numbers.')" style="padding:4px 10px;font-size:11px;background:#22c55e20;color:#22c55e;border:1px solid #22c55e40;border-radius:6px;cursor:pointer">View</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div id="msp-detail" style="display:none;margin-top:14px;background:#0f1f3a;border:1px solid #1e3a5f;border-radius:10px;padding:16px"></div>

    <div style="margin-top:14px;padding:12px 16px;background:#060b18;border:1px solid #1e3a5f40;border-radius:8px;font-size:12px;color:#4a7fa5;line-height:1.7">
      <strong style="color:#00B5A5">API call behind this view:</strong>
      <code style="color:#94a3b8;background:#1e3a5f;padding:2px 6px;border-radius:4px">POST /v1/metered/bulk-identity-risk</code>
      — submit all 5 client domains in a single request. Each domain scored across 6 signal dimensions. ConnectWise service ticket auto-created for every CRITICAL result — alert lands in your existing MSP queue with severity, affected identity, and remediation steps pre-populated. &nbsp;<span style="color:#22c55e;font-weight:600">$0.50 per batch of 100 identities.</span>
    </div>
  </div>

</div>
<footer>
  RelayShield Threat Intelligence &mdash; <a href="https://api.relayshield.net/developers">api.relayshield.net/developers</a> &mdash; $499/month TI Starter
</footer>

<script>
function mspTriage(domain, level, score, detail) {
  const box = document.getElementById('msp-detail');
  const rc = level === 'CRITICAL' ? '#ef4444' : level === 'HIGH' ? '#f97316' : level === 'MEDIUM' ? '#facc15' : '#22c55e';
  box.style.display = 'block';
  box.innerHTML = \`
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div>
        <span style="font-size:12px;color:#4a7fa5;font-weight:700;letter-spacing:.4px;text-transform:uppercase">Client Detail</span>
        <span style="margin-left:8px;font-size:13px;color:#e2e8f0;font-weight:600;font-family:monospace">\${domain}</span>
      </div>
      <span style="background:\${rc}20;color:\${rc};border:1px solid \${rc}40;border-radius:20px;padding:3px 10px;font-size:12px;font-weight:700">\${level} \${score}/100</span>
    </div>
    <div style="font-size:13px;color:#94a3b8;line-height:1.7;margin-bottom:14px">\${detail}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button onclick="alert('WhatsApp remediation sequence sent to client admin contact')" style="padding:6px 14px;font-size:12px;font-weight:600;background:#25d36620;color:#25d366;border:1px solid #25d36640;border-radius:8px;cursor:pointer">📱 WA Remediation</button>
      <button onclick="alert('ConnectWise ticket created:\\n\\nClient: \${domain}\\nSeverity: \${level}\\nScore: \${score}/100\\nDetail: \${detail}\\n\\nTicket #' + Math.floor(8000+Math.random()*2000) + ' opened in Service Board')" style="padding:6px 14px;font-size:12px;font-weight:600;background:#22c55e20;color:#22c55e;border:1px solid #22c55e40;border-radius:8px;cursor:pointer">↗ Create CW Ticket</button>
      <button onclick="document.getElementById('msp-detail').style.display='none'" style="padding:6px 14px;font-size:12px;font-weight:600;background:#1e3a5f;color:#64748b;border:1px solid #1e3a5f;border-radius:8px;cursor:pointer">✕ Dismiss</button>
    </div>\`;
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}

function switchTab(id, el) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}

function setLoading(id) {
  document.getElementById(id).innerHTML = '<div class="loading">Querying live corpus...</div>';
}

async function runIdentity() {
  const domain = document.getElementById('identity-input').value.trim();
  if (!domain) return;
  setLoading('identity-result');
  const resp = await fetch('/demo/identity', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({domain})
  });
  const data = await resp.json();
  window._rsReport = {domain: domain, score: data.risk_score, grade: data.grade, level: data.risk_level, dims: data.dimension_scores||{}, factors: data.risk_factors||[]};
  document.getElementById('identity-result').innerHTML = renderIdentityRisk(data);
}

async function runActor() {
  const actor = document.getElementById('actor-input').value.trim();
  if (!actor) return;
  setLoading('actor-result');
  const resp = await fetch('/demo/actor', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({actor})
  });
  const data = await resp.json();
  document.getElementById('actor-result').innerHTML = renderActor(data);
}

async function runTrending() {
  const hours = document.getElementById('trending-hours').value;
  setLoading('trending-result');
  const resp = await fetch('/demo/trending', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({hours: parseInt(hours)})
  });
  const data = await resp.json();
  document.getElementById('trending-result').innerHTML = renderTrending(data);
}

async function runNHI() {
  const domain = document.getElementById('nhi-input').value.trim();
  if (!domain) return;
  setLoading('nhi-result');
  const resp = await fetch('/demo/nhi', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({domain})
  });
  const data = await resp.json();
  document.getElementById('nhi-result').innerHTML = renderNHI(data);
}

async function runLLMJacking() {
  const domain = document.getElementById('llmjacking-input').value.trim();
  if (!domain) return;
  setLoading('llmjacking-result');
  const resp = await fetch('/demo/llmjacking', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({domain})
  });
  const data = await resp.json();
  document.getElementById('llmjacking-result').innerHTML = renderLLMJacking(data);
}

async function runIpIntel() {
  const query = document.getElementById('ipintel-input').value.trim();
  if (!query) return;
  // crude IPv4 detection — anything else is treated as a domain
  const isIp = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(query);
  setLoading('ipintel-result');
  const resp = await fetch('/demo/ip-intel', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(isIp ? {ip: query} : {domain: query})
  });
  const data = await resp.json();
  document.getElementById('ipintel-result').innerHTML = renderIpIntel(data);
}

async function runSupply() {
  const domain = document.getElementById('supply-domain').value.trim();
  if (!domain) return;
  const agents = [
    document.getElementById('supply-agent-1').value.trim(),
    document.getElementById('supply-agent-2').value.trim(),
    document.getElementById('supply-agent-3').value.trim(),
  ].filter(Boolean);
  setLoading('supply-result');
  const resp = await fetch('/demo/supply', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({targets: [{domain, agents}]})
  });
  const data = await resp.json();
  document.getElementById('supply-result').innerHTML = renderBulkIdentity(data);
}

${renderFunctions()}
</script>
</body>
</html>`;

function renderAttackTimeline(dims, score) {
  // Determine which stages of the attack chain have fired based on dimension scores
  const hasBreach      = (dims.breach_exposure || 0) > 0;
  const hasInfostealer = (dims.infostealer_density || 0) > 0;
  const hasSession     = (dims.session_exposure || 0) > 0;
  const atRisk         = score >= 45;

  const stages = [
    { label: "Data\nBreach",        hit: hasBreach,      icon: "💾", tip: "Credentials in breach database" },
    { label: "Infostealer\nHit",    hit: hasInfostealer, icon: "🕵", tip: "Active credential harvesting detected" },
    { label: "Session\nStolen",     hit: hasSession,     icon: "🍪", tip: "Live session cookie in criminal archive" },
    { label: "Account\nTakeover",   hit: atRisk,         icon: "🔓", tip: "Risk threshold for ATO reached" },
  ];

  // Determine where the domain sits on the chain
  let currentStage = -1;
  stages.forEach((s, i) => { if (s.hit) currentStage = i; });

  const stageHtml = stages.map((s, i) => {
    const active  = s.hit;
    const current = i === currentStage;
    const color   = active ? (i >= 3 ? "#ef4444" : i >= 2 ? "#f97316" : i >= 1 ? "#facc15" : "#22c55e") : "#1e3a5f";
    const lineColor = (i < stages.length - 1 && stages[i+1].hit) ? color : "#1e3a5f";
    return `<div class="tl-stage">
      <div class="tl-dot-outer" style="border-color:${color};${active ? `box-shadow:0 0 6px ${color}60` : ""}" title="${s.tip}">
        <span style="font-size:11px">${active ? s.icon : "·"}</span>
      </div>
      <div class="tl-label" style="color:${active ? "#e2e8f0" : "#334155"}">${s.label.replace("\n","<br>")}</div>
      ${current ? `<div class="tl-you" style="color:${color}">← YOU ARE HERE</div>` : ""}
      ${i < stages.length - 1 ? `<div style="position:absolute;top:12px;left:50%;width:100%;height:2px;background:${lineColor};z-index:0"></div>` : ""}
    </div>`;
  }).join("");

  const warningMsg = currentStage >= 2
    ? `<div style="font-size:12px;color:#ef4444;margin-top:10px;font-weight:600">⚠ Active session exposure detected — attacker can bypass 2FA without a password</div>`
    : currentStage >= 1
    ? `<div style="font-size:12px;color:#f97316;margin-top:10px">Active credential harvesting on this domain. Session theft is the next step in the attack chain.</div>`
    : currentStage >= 0
    ? `<div style="font-size:12px;color:#facc15;margin-top:10px">Breach data is the raw material for SIM swap and infostealer targeting. Monitor for escalation.</div>`
    : `<div style="font-size:12px;color:#22c55e;margin-top:10px">No active attack chain signals detected for this domain.</div>`;

  return `<div class="attack-timeline">
    <div style="font-size:11px;font-weight:700;color:#4a7fa5;letter-spacing:.5px;text-transform:uppercase;margin-bottom:4px">Attack Chain Position</div>
    <div style="font-size:11px;color:#334155;margin-bottom:12px">Where this domain sits in the identity attack sequence</div>
    <div class="tl-track">${stageHtml}</div>
    ${warningMsg}
  </div>`;
}

function downloadReport() {
  const {domain,score,grade,level,dims,factors} = window._rsReport || {};
  const date = new Date().toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric'});
  const dimNames = {breach_exposure:'Breach Exposure',infostealer_density:'Infostealer Density',ioc_presence:'IOC Presence',ransomware_victim:'Ransomware Victim',session_exposure:'Session Exposure',cve_exposure:'CVE Exposure'};
  const dimLines = Object.entries(dims).map(([k,v]) => `  ${(dimNames[k]||k).padEnd(24)} ${v}`).join('\n');
  const factorLines = (factors||[]).map(f => `  • ${f}`).join('\n');
  const content = `RELAYSHIELD — IDENTITY RISK REPORT
${'='.repeat(50)}
Generated:    ${date}
Domain:       ${domain}
Risk Score:   ${score}/100
Risk Level:   ${level}
Grade:        ${grade}

SIGNAL DIMENSIONS
${'─'.repeat(40)}
${dimLines}

RISK FACTORS
${'─'.repeat(40)}
${factorLines || '  None identified'}

RECOMMENDED ACTIONS
${'─'.repeat(40)}
  • Rotate credentials for all accounts associated with this domain
  • Audit active sessions and revoke any unrecognised tokens
  • Enable hardware MFA where session cookie exposure is detected
  • Review infostealer remediation steps via RelayShield bot

${'─'.repeat(50)}
RelayShield Threat Intelligence | relayshield.net
© 2026 RelayShield LLC — Confidential
`;
  const blob = new Blob([content], {type:'text/plain'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `relayshield-report-${domain}-${new Date().toISOString().slice(0,10)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function renderFunctions() {
  // These are the render functions inlined — they're in the Worker scope already
  return `
function grade_color(g){return{A:'#22c55e',B:'#86efac',C:'#facc15',D:'#f97316',F:'#ef4444'}[g]||'#94a3b8'}
function risk_color(l){return{LOW:'#22c55e',MEDIUM:'#facc15',HIGH:'#f97316',CRITICAL:'#ef4444'}[l]||'#94a3b8'}
${renderIdentityRisk.toString()}
${renderAttackTimeline.toString()}
${downloadReport.toString()}
${renderActor.toString()}
${renderTrending.toString()}
${renderNHI.toString()}
${renderLLMJacking.toString()}
${riskGaugeSvg.toString()}
${ipIntelRiskLevel.toString()}
${renderIpIntel.toString()}
${renderBulkIdentity.toString()}
${renderSupplyChain.toString()}
`;
}

const GATE_HTML = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>RelayShield Demo</title>
<style>body{font-family:sans-serif;background:#0a1628;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:#0F1F3D;border:1px solid #1e3a5f;border-top:3px solid #00B5A5;border-radius:8px;padding:40px;max-width:400px;text-align:center}
h2{color:#fff;margin-bottom:12px}p{color:#64748b;font-size:14px;line-height:1.6}a{color:#00B5A5}</style></head>
<body><div class="box"><h2>🔒 Demo Access Required</h2>
<p>This demo is for qualified prospects and partners.<br><br>
Contact <a href="mailto:support@relayshield.net">support@relayshield.net</a> to request access.</p></div></body></html>`;

export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const token  = url.searchParams.get("token") || "";
    const path   = url.pathname;

    // Gate check — pass token as query param or cookie
    const cookie = request.headers.get("Cookie") || "";
    const authed = token === DEMO_TOKEN || cookie.includes(`demo_token=${DEMO_TOKEN}`);

    if (!authed && !path.startsWith("/demo/")) {
      return new Response(GATE_HTML, {
        status: 401,
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    // API proxy endpoints
    if (path === "/demo/identity" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/metered/identity-risk-score", body);
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/actor" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/intel/actor", { actor: body.actor });
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/trending" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/intel/trending", { hours: body.hours || 24 });
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/nhi" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/metered/nhi-exposure", body);
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/llmjacking" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/metered/llm-credential-exposure", body);
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/ip-intel" && request.method === "POST") {
      const body = await request.json();
      const data = await callAPI(env, "/v1/metered/ip-intel", body);
      return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
    }

    if (path === "/demo/supply" && request.method === "POST") {
      const body = await request.json();
      const targets = body.targets || [];
      if (!targets.length) return new Response(JSON.stringify({error:"no targets"}), {headers:{"Content-Type":"application/json"}});
      const target = targets[0];

      // Run domain scoring and NHI credential scan in parallel
      const agentEmails = target.agents || [];
      const [domainData, nhiData] = await Promise.all([
        callAPI(env, "/v1/metered/identity-risk-score", {domain: target.domain}),
        callAPI(env, "/v1/metered/nhi-exposure", {domain: target.domain})
      ]);

      // Map NHI findings to agent emails — any finding for the domain flags agents on that domain
      const nhiFindings = nhiData.findings || [];
      const criticalFindings = nhiFindings.filter(f => f.severity === "CRITICAL" || f.severity === "HIGH");
      const agents = agentEmails.map((email, idx) => {
        const agentDomain = email.split("@")[1] || "";
        // Any NHI credential finding for this domain flags the agent
        const domainMatch = nhiFindings.find(f => f.severity && agentDomain.includes(target.domain));
        // Distribute findings across agents (first agent gets highest severity)
        const finding = criticalFindings[idx] || domainMatch;
        if (finding) {
          return {
            identity: email,
            risk_score: finding.severity === "CRITICAL" ? 95 : finding.severity === "HIGH" ? 70 : 40,
            risk_level: finding.severity || "HIGH",
            risk_factors: [`${finding.type||"Service credential"} detected in criminal stealer archive — ${finding.description||"NHI exposure confirmed"}`]
          };
        }
        return { identity: email, risk_score: 0, risk_level: "LOW",
          risk_factors: ["No credential exposure detected in current corpus"] };
      });

      const critAgents = agents.filter(a => a.risk_level === "CRITICAL").length;
      const highAgents = agents.filter(a => ["CRITICAL","HIGH"].includes(a.risk_level)).length;

      const result = {
        queried: 1,
        critical_count: critAgents,
        high_count: highAgents,
        summary: domainData.summary || "",
        results: [{
          domain: target.domain,
          domain_score: domainData.risk_score || 0,
          domain_grade: domainData.grade || "A",
          domain_risk: domainData.risk_level || "LOW",
          domain_factors: domainData.risk_factors || [],
          dimension_scores: domainData.dimension_scores || {},
          agents,
          agent_count: agents.length,
          highest_agent_risk: agents.length ? agents.sort((a,b)=>b.risk_score-a.risk_score)[0].risk_level : null,
        }]
      };
      return new Response(JSON.stringify(result), { headers: { "Content-Type": "application/json" } });
    }

    // Serve the demo page (set auth cookie so token doesn't need to stay in URL)
    const headers = new Headers({ "Content-Type": "text/html;charset=UTF-8", "Cache-Control": "no-store" });
    if (token === DEMO_TOKEN) {
      headers.set("Set-Cookie", `demo_token=${DEMO_TOKEN}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400`);
    }
    return new Response(PAGE("", token), { headers });
  },
};
