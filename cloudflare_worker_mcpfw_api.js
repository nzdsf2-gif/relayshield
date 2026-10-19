/**
 * RelayShield MCP Firewall Console Backend API
 *
 * Serves the console UI and provides REST endpoints for all 9 tabs.
 * Storage: Cloudflare KV (CONFIG_KV for servers/policies/quarantine,
 * AUDIT_KV for audit logs, KEYS_KV for API key metadata).
 *
 * LIVE: /api/keys queries DynamoDB relayshield_api_keys directly.
 * LIVE: /api/billing queries Stripe API for subscriptions and invoices.
 * TODO: Wire /api/verifiers to TAP/PAP Lambda logs.
 */

const JSON_HEADERS = {
  "Content-Type": "application/json",
  "Cache-Control": "no-store",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, x-api-key",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function error(message, status = 400) {
  return json({ error: message }, status);
}

// --- Auth helper (preview: accepts any key, logs it) ---
// TODO: Replace with real session auth + RBAC (admin/operator/viewer).
async function getAuth(request, env) {
  const apiKey = request.headers.get("x-api-key");
  // Preview mode: allow without key, mark as preview
  return { apiKey: apiKey || "preview", role: "admin", preview: !apiKey };
}

const AWS_REGION = "us-east-1";
const DYNAMODB_ENDPOINT = `https://dynamodb.${AWS_REGION}.amazonaws.com`;
const KEYS_TABLE = "relayshield_api_keys";
const RATE_LIMITS_TABLE = "relayshield_rate_limits";

// --- SigV4 signing helpers ---
async function sha256Hex(data) {
  const buf = typeof data === "string" ? new TextEncoder().encode(data) : data;
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256(key, data) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw", typeof key === "string" ? new TextEncoder().encode(key) : key,
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "HMAC", cryptoKey, typeof data === "string" ? new TextEncoder().encode(data) : data
  );
  return new Uint8Array(sig);
}

async function getSignatureKey(secretKey, dateStamp, region, service) {
  const kDate = await hmacSha256("AWS4" + secretKey, dateStamp);
  const kRegion = await hmacSha256(kDate, region);
  const kService = await hmacSha256(kRegion, service);
  return hmacSha256(kService, "aws4_request");
}

async function dynamoRequest(env, action, payload) {
  const accessKey = env.AWS_ACCESS_KEY_ID;
  const secretKey = env.AWS_SECRET_ACCESS_KEY;
  const region = env.AWS_REGION || AWS_REGION;

  if (!accessKey || !secretKey) {
    throw new Error("AWS credentials not configured");
  }

  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.substring(0, 8);

  const body = JSON.stringify(payload);
  const bodyHash = await sha256Hex(body);

  const headers = {
    "Content-Type": "application/x-amz-json-1.0",
    "X-Amz-Date": amzDate,
    "X-Amz-Target": `DynamoDB_20120810.${action}`,
  };

  // Canonical request
  const signedHeaders = "content-type;host;x-amz-date;x-amz-target";
  const canonicalHeaders = `content-type:${headers["Content-Type"]}\n` +
    `host:dynamodb.${region}.amazonaws.com\n` +
    `x-amz-date:${amzDate}\n` +
    `x-amz-target:${headers["X-Amz-Target"]}\n`;

  const canonicalRequest = [
    "POST", "/", "",
    canonicalHeaders, signedHeaders, bodyHash,
  ].join("\n");

  const credentialScope = `${dateStamp}/${region}/dynamodb/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256", amzDate, credentialScope,
    await sha256Hex(canonicalRequest),
  ].join("\n");

  const signingKey = await getSignatureKey(secretKey, dateStamp, region, "dynamodb");
  const signature = [...await hmacSha256(signingKey, stringToSign)]
    .map(b => b.toString(16).padStart(2, "0")).join("");

  const authHeader = `AWS4-HMAC-SHA256 Credential=${accessKey}/${credentialScope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  const res = await fetch(`https://dynamodb.${region}.amazonaws.com/`, {
    method: "POST",
    headers: { ...headers, Authorization: authHeader },
    body,
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`DynamoDB ${action} failed: ${res.status} ${errText}`);
  }

  return res.json();
}

// --- API Key operations against DynamoDB ---
async function dynamoGetKey(env, apiKey) {
  const result = await dynamoRequest(env, "GetItem", {
    TableName: KEYS_TABLE,
    Key: { api_key: { S: apiKey } },
  });
  return result.Item || null;
}

async function dynamoScanKeys(env) {
  // Returns all keys (metadata only). For large tables, add pagination.
  //
  // BILLING MODEL: Billing is per customer_id (Stripe customer), NOT per key.
  // A customer organization may have multiple keys with different RBAC roles
  // (admin, operator, viewer) under the same stripe_customer_id. All keys
  // under one customer_id are covered by that customer's single Stripe
  // subscription. Roles control what each key can do; they do not create
  // separate billing entities.
  const result = await dynamoRequest(env, "Scan", {
    TableName: KEYS_TABLE,
    ProjectionExpression: "api_key, #n, sku, active, stripe_customer_id, created_at, #r, label",
    ExpressionAttributeNames: { "#n": "name", "#r": "role" },
    Limit: 100,
  });

  const keys = (result.Items || []).map(item => ({
    // Never return the full key value in listings
    prefix: item.api_key?.S?.substring(0, 8) + "...",
    name: item.name?.S || "",
    label: item.label?.S || item.name?.S || "",
    role: item.role?.S || "viewer", // admin | operator | viewer
    sku: item.sku?.S || "",
    active: item.active?.BOOL || false,
    // customer_id groups keys for billing: one Stripe subscription per customer,
    // regardless of how many keys (roles) they have.
    customer_id: item.stripe_customer_id?.S || "",
    stripe_customer_id: item.stripe_customer_id?.S || "",
    created_at: item.created_at?.S || "",
  }));

  // Group by customer_id for the response so the console can show
  // "one customer, N keys, billed once."
  const byCustomer = {};
  for (const k of keys) {
    const cid = k.customer_id || "unassigned";
    if (!byCustomer[cid]) byCustomer[cid] = [];
    byCustomer[cid].push(k);
  }

  return { keys, by_customer: byCustomer };
}


// --- Servers ---
async function handleServers(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method === "GET") {
    const groups = await env.CONFIG_KV.get("server_groups", "json") || [];
    return json({ groups });
  }

  if (request.method === "POST") {
    const body = await request.json();
    // body: { group_id, server: { id, name, upstream_url, proxy_path, policy_override } }
    const groups = await env.CONFIG_KV.get("server_groups", "json") || [];
    const group = groups.find(g => g.id === body.group_id);
    if (!group) return error("Group not found", 404);
    group.servers.push({ ...body.server, status: "healthy", reputation: 100, added_at: new Date().toISOString() });
    await env.CONFIG_KV.put("server_groups", JSON.stringify(groups));
    await logAudit(env, ctx, "server.added", { group_id: body.group_id, server_id: body.server.id });
    return json({ ok: true, server: body.server }, 201);
  }

  return error("Method not allowed", 405);
}

// --- Policies ---
async function handlePolicies(request, env, ctx) {
  if (request.method === "GET") {
    const policies = await env.CONFIG_KV.get("policies", "json") || [];
    return json({ policies });
  }

  if (request.method === "PUT") {
    const body = await request.json();
    // body: { policy_id, policy: {...} } or { policy_id, json_import: "..." }
    const policies = await env.CONFIG_KV.get("policies", "json") || [];
    const idx = policies.findIndex(p => p.id === body.policy_id);

    let policyData = body.policy;
    if (body.json_import) {
      try {
        policyData = JSON.parse(body.json_import);
      } catch (e) {
        return error("Invalid JSON in policy import");
      }
    }

    if (idx >= 0) {
      policies[idx] = { ...policies[idx], ...policyData, updated_at: new Date().toISOString() };
    } else {
      policies.push({ id: body.policy_id, ...policyData, created_at: new Date().toISOString() });
    }

    await env.CONFIG_KV.put("policies", JSON.stringify(policies));
    await logAudit(env, ctx, "policy.updated", { policy_id: body.policy_id });
    return json({ ok: true });
  }

  return error("Method not allowed", 405);
}

// --- Quarantine ---
async function handleQuarantine(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method === "GET") {
    const items = await env.CONFIG_KV.get("quarantine", "json") || [];
    const duration = await env.CONFIG_KV.get("quarantine_duration_hours") || "24";

    // Attach trigger event confidence for items that don't have it stored.
    // Looks up recent screening verdicts for the quarantined server in the audit log.
    let auditEntries = null;
    const enriched = await Promise.all(items.map(async (item) => {
      if (item.trigger_events) return item; // already stored
      try {
        if (!auditEntries) auditEntries = await env.AUDIT_KV.get("audit_log", "json") || [];
        const serverId = item.server_id || item.server;
        const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000; // last 7 days
        const triggers = auditEntries
          .filter(e => {
            const d = e.details || {};
            const matchServer = d.server_id === serverId || d.server === serverId;
            const hasConf = typeof d.confidence === "number";
            const isScreening = (e.event_type || "").startsWith("screening.");
            return matchServer && hasConf && isScreening && new Date(e.timestamp).getTime() >= cutoff;
          })
          .slice(-5) // most recent 5 trigger candidates
          .map(e => ({
            event_id: e.id,
            confidence: e.details.confidence,
            confidence_source: e.details.confidence_source || null,
            tool: e.details.tool || null,
            timestamp: e.timestamp,
          }));
        const avg = triggers.length
          ? Math.round((triggers.reduce((s, t) => s + t.confidence, 0) / triggers.length) * 1000) / 1000
          : null;
        return { ...item, trigger_events: triggers, avg_trigger_confidence: avg };
      } catch (e) {
        console.error("Quarantine trigger enrichment failed:", e);
        return item;
      }
    }));

    return json({ items: enriched, quarantine_duration_hours: parseInt(duration), violation_threshold: parseInt(await env.CONFIG_KV.get("quarantine_violation_threshold") || "5", 10) });
  }

  if (request.method === "POST") {
    const body = await request.json();
    // body: { action: "release"|"extend"|"set_duration"|"set_threshold", server_id?, duration_hours?, threshold? }

    if (body.action === "set_duration") {
      await env.CONFIG_KV.put("quarantine_duration_hours", String(body.duration_hours));
      await logAudit(env, ctx, "quarantine.duration_changed", { hours: body.duration_hours });
      return json({ ok: true });
    }

    if (body.action === "set_threshold") {
      const t = parseInt(body.threshold, 10);
      if (!Number.isFinite(t) || t < 1 || t > 100) {
        return error("threshold must be an integer between 1 and 100", 400);
      }
      await env.CONFIG_KV.put("quarantine_violation_threshold", String(t));
      await logAudit(env, ctx, "quarantine.threshold_changed", { threshold: t });
      return json({ ok: true, threshold: t });
    }

    const items = await env.CONFIG_KV.get("quarantine", "json") || [];
    if (body.action === "release") {
      const filtered = items.filter(i => i.server_id !== body.server_id);
      await env.CONFIG_KV.put("quarantine", JSON.stringify(filtered));
      await logAudit(env, ctx, "quarantine.released", { server_id: body.server_id });
      return json({ ok: true });
    }

    return error("Unknown quarantine action");
  }

  return error("Method not allowed", 405);
}

// --- Audit ---
async function handleAudit(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method === "GET") {
    const limit = parseInt(url.searchParams.get("limit") || "100");
    const offset = parseInt(url.searchParams.get("offset") || "0");
    const eventType = url.searchParams.get("event_type");
    const serverId = url.searchParams.get("server_id");

    let entries = await env.AUDIT_KV.get("audit_log", "json") || [];
    if (eventType) {
      entries = entries.filter(e => e.event_type === eventType);
    }
    if (serverId) {
      entries = entries.filter(e => e.details && e.details.server_id === serverId);
    }
    // Newest first
    entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    const total = entries.length;
    const page = entries.slice(offset, offset + limit);

    return json({ entries: page, total, limit, offset });
  }

  return error("Method not allowed", 405);
}

async function logAudit(env, ctx, eventType, details) {
  try {
    let entries = await env.CONFIG_KV.get("audit_log", "json") || [];
    const newEntry = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      event_type: eventType,
      details,
      actor: "api", // TODO: real user identity from session
    };
    entries.push(newEntry);
    // Keep last 5000 entries (90-day retention handled by separate cleanup)
    if (entries.length > 5000) entries = entries.slice(-5000);
    ctx.waitUntil(env.CONFIG_KV.put("audit_log", JSON.stringify(entries)));

    // Auto-quarantine: on screening.blocked, increment per-server violation
    // counter. If counter >= quarantine_violation_threshold (default 5),
    // automatically quarantine the server.
    if (eventType === "screening.blocked" && details && details.server_id) {
      ctx.waitUntil(checkAutoQuarantine(env, details.server_id, newEntry.id));
    }
  } catch (e) {
    console.error("Audit log failed:", e);
  }
}

// Auto-quarantine helper: increments the 24h violation counter for a server
// and quarantines it when the counter reaches the configured threshold.
async function checkAutoQuarantine(env, serverId, triggerEventId) {
  try {
    const threshold = parseInt(await env.CONFIG_KV.get("quarantine_violation_threshold") || "5", 10);
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;

    // Count screening.blocked events for this server in the last 24h.
    // NOTE: reads CONFIG_KV (audit writes go there); see logAudit above.
    const entries = await env.CONFIG_KV.get("audit_log", "json") || [];
    const violations = entries.filter(e =>
      e.event_type === "screening.blocked" &&
      e.details && e.details.server_id === serverId &&
      new Date(e.timestamp).getTime() >= cutoff
    );

    if (violations.length >= threshold) {
      const items = await env.CONFIG_KV.get("quarantine", "json") || [];
      const already = items.some(i => i.server_id === serverId);
      if (!already) {
        const triggerIds = violations.slice(-5).map(v => v.id);
        items.push({
          server_id: serverId,
          quarantined_at: new Date().toISOString(),
          reason: `auto-quarantine: ${violations.length} violations in 24h`,
          trigger_event_ids: triggerIds,
          auto: true,
        });
        await env.CONFIG_KV.put("quarantine", JSON.stringify(items));
        console.log(`Auto-quarantined ${serverId} (${violations.length} violations >= ${threshold})`);
      }
    }
  } catch (e) {
    console.error("Auto-quarantine check failed:", e);
  }
}

// --- Telemetry ---
async function handleTelemetry(request, env, ctx) {
  if (request.method === "GET") {
    const enabled = await env.CONFIG_KV.get("telemetry_enabled") || "false";
    const level = await env.CONFIG_KV.get("telemetry_level") || "counts";
    return json({
      enabled: enabled === "true",
      level,
      // Never expose corpus review queue to customers
    });
  }

  if (request.method === "POST") {
    const body = await request.json();
    // body: { enabled: boolean, level: "counts"|"indicators" }
    await env.CONFIG_KV.put("telemetry_enabled", String(body.enabled));
    if (body.level) await env.CONFIG_KV.put("telemetry_level", body.level);
    await logAudit(env, ctx, "telemetry.updated", { enabled: body.enabled, level: body.level });
    return json({ ok: true, enabled: body.enabled, level: body.level || "counts" });
  }

  return error("Method not allowed", 405);
}

// --- API Keys (DynamoDB live) ---
async function handleKeys(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method === "GET" && url.pathname === "/api/keys") {
    try {
      const { keys, by_customer } = await dynamoScanKeys(env);
      return json({
        keys,
        by_customer,
        source: "dynamodb",
        billing_note: "Billing is per customer_id, not per key. Multiple keys (admin/operator/viewer) under the same customer_id are charged once via their Stripe subscription.",
      });
    } catch (e) {
      console.error("DynamoDB scan failed:", e);
      return error("Failed to list API keys: " + e.message, 502);
    }
  }

  // POST (create) and DELETE (revoke) still need design decisions:
  // - Key generation: who mints the raw key? (recommend: Lambda or Worker with crypto)
  // - Hashing: store SHA-256 hash, not raw key (TODO)
  // For now, return 501 with guidance.
  if (request.method === "POST" || request.method === "DELETE") {
    return error(
      "Key creation/revocation via API not yet implemented. " +
      "Use AWS Console or CLI to manage relayshield_api_keys directly.", 501
    );
  }

  return error("Method not allowed", 405);
}

// --- Verifiers (CloudWatch live) ---
async function handleVerifiers(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method !== "GET") {
    return error("Method not allowed", 405);
  }

  const type = url.searchParams.get("type") || "all"; // tap, pap, all
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "50"), 100);
  const hours = Math.min(parseInt(url.searchParams.get("hours") || "24"), 168); // max 7d

  if (!env.AWS_ACCESS_KEY_ID || !env.AWS_SECRET_ACCESS_KEY) {
    return error("AWS credentials not configured", 503);
  }

  const region = env.AWS_REGION || "us-east-1";
  const endTime = Math.floor(Date.now() / 1000);
  const startTime = endTime - (hours * 3600);

  const logGroups = [];
  if (type === "all" || type === "tap") {
    logGroups.push("/aws/lambda/relayshield-tap-verifier");
  }
  if (type === "all" || type === "pap") {
    logGroups.push("/aws/lambda/relayshield-pap-verifier");
  }

  try {
    const results = {};

    for (const logGroup of logGroups) {
      const label = logGroup.includes("tap") ? "tap" : "pap";

      // Start Insights query for verification events
      const queryString = `
        fields @timestamp, @message
        | filter @message like /verdict/ or @message like /VERDICT/ or @message like /verification/
        | sort @timestamp desc
        | limit ${limit}
      `;

      const queryId = await cwStartQuery(env, region, logGroup, startTime, endTime, queryString);

      // Poll for results (max ~10 seconds)
      let queryResults = null;
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 500));
        queryResults = await cwGetQueryResults(env, region, queryId);
        if (queryResults.status === "Complete") break;
        if (queryResults.status === "Failed" || queryResults.status === "Cancelled") {
          throw new Error(`Query ${queryResults.status}`);
        }
      }

      if (!queryResults || queryResults.status !== "Complete") {
        results[label] = { enabled: true, logs: [], total: 0, note: "Query timed out" };
        continue;
      }

      const logs = (queryResults.results || []).map(row => {
        const entry = {};
        for (const field of row) {
          entry[field.field] = field.value;
        }
        // Try to parse the message as JSON for structured data
        let parsed = null;
        try {
          parsed = JSON.parse(entry["@message"] || "{}");
        } catch (e) { /* not JSON */ }

        return {
          timestamp: entry["@timestamp"] || "",
          message: (entry["@message"] || "").substring(0, 500),
          verdict: parsed?.verdict || parsed?.result || null,
          token_hash: parsed?.token_hash || parsed?.jti || null,
        };
      });

      results[label] = {
        enabled: true,
        logs,
        total: logs.length,
        log_group: logGroup,
      };
    }

    return json(results);

  } catch (e) {
    console.error("CloudWatch query failed:", e);
    return json({
      tap: { enabled: true, logs: [], total: 0, error: e.message },
      pap: { enabled: true, logs: [], total: 0, error: e.message },
      note: "Failed to query CloudWatch. Check IAM permissions for logs:StartQuery.",
    });
  }
}

// --- CloudWatch Logs API helpers (SigV4 signed) ---

async function cwSignedRequest(env, region, action, payload) {
  const accessKey = env.AWS_ACCESS_KEY_ID;
  const secretKey = env.AWS_SECRET_ACCESS_KEY;

  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.substring(0, 8);

  const body = JSON.stringify(payload);
  const bodyHash = await sha256Hex(body);

  const service = "logs";
  const host = `logs.${region}.amazonaws.com`;

  const headers = {
    "Content-Type": "application/x-amz-json-1.1",
    "X-Amz-Date": amzDate,
    "X-Amz-Target": `Logs_20140328.${action}`,
  };

  const signedHeaders = "content-type;host;x-amz-date;x-amz-target";
  const canonicalHeaders =
    `content-type:${headers["Content-Type"]}\n` +
    `host:${host}\n` +
    `x-amz-date:${amzDate}\n` +
    `x-amz-target:${headers["X-Amz-Target"]}\n`;

  const canonicalRequest = ["POST", "/", "", canonicalHeaders, signedHeaders, bodyHash].join("\n");
  const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
  const stringToSign = ["AWS4-HMAC-SHA256", amzDate, credentialScope, await sha256Hex(canonicalRequest)].join("\n");

  const signingKey = await getSignatureKey(secretKey, dateStamp, region, service);
  const signature = [...await hmacSha256(signingKey, stringToSign)]
    .map(b => b.toString(16).padStart(2, "0")).join("");

  const authHeader = `AWS4-HMAC-SHA256 Credential=${accessKey}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;

  const res = await fetch(`https://${host}/`, {
    method: "POST",
    headers: { ...headers, Authorization: authHeader },
    body,
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`CloudWatch ${action} failed: ${res.status} ${errText.substring(0, 200)}`);
  }

  return res.json();
}

async function cwStartQuery(env, region, logGroupName, startTime, endTime, queryString) {
  const result = await cwSignedRequest(env, region, "StartQuery", {
    logGroupName,
    startTime,
    endTime,
    queryString,
    limit: 100,
  });
  return result.queryId;
}

async function cwGetQueryResults(env, region, queryId) {
  return cwSignedRequest(env, region, "GetQueryResults", { queryId });
}

// --- Billing (Stripe live) ---
async function handleBilling(request, env, ctx) {
  const auth = await getAuth(request, env);

  if (request.method === "GET") {
    const url = new URL(request.url);
    const customerId = url.searchParams.get("customer_id") || auth.stripeCustomerId;

    if (!customerId) {
      return json({
        subscription: null,
        usage: null,
        portal_url: null,
        note: "No Stripe customer linked. Provide ?customer_id= or link via API key metadata.",
      });
    }

    if (!env.STRIPE_SECRET_KEY) {
      return error("Stripe not configured", 503);
    }

    try {
      // Get active subscriptions
      const subsRes = await fetch(
        `https://api.stripe.com/v1/subscriptions?customer=${customerId}&status=active&limit=5`,
        {
          headers: {
            Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
          },
        }
      );
      const subs = await subsRes.json();

      // Get recent invoices
      const invRes = await fetch(
        `https://api.stripe.com/v1/invoices?customer=${customerId}&limit=10`,
        {
          headers: {
            Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
          },
        }
      );
      const invoices = await invRes.json();

      const activeSub = subs.data?.[0] || null;

      return json({
        subscription: activeSub ? {
          id: activeSub.id,
          status: activeSub.status,
          product_name: activeSub.items?.data?.[0]?.price?.nickname || "Unknown",
          amount: activeSub.items?.data?.[0]?.price?.unit_amount / 100,
          currency: activeSub.currency?.toUpperCase(),
          current_period_end: new Date(activeSub.current_period_end * 1000).toISOString(),
          cancel_at_period_end: activeSub.cancel_at_period_end,
        } : null,
        invoices: (invoices.data || []).map(inv => ({
          id: inv.id,
          amount: inv.amount_due / 100,
          currency: inv.currency?.toUpperCase(),
          status: inv.status,
          created: new Date(inv.created * 1000).toISOString(),
          pdf_url: inv.invoice_pdf,
        })),
        portal_note: "Use Stripe Customer Portal for self-service subscription management.",
      });
    } catch (e) {
      console.error("Stripe API error:", e);
      return error("Failed to fetch billing data", 502);
    }
  }

  if (request.method === "POST") {
    const body = await request.json();
    // body: { action: "create_portal_session", customer_id, return_url }

    if (body.action === "create_portal_session") {
      if (!env.STRIPE_SECRET_KEY) {
        return error("Stripe not configured", 503);
      }

      try {
        const params = new URLSearchParams();
        params.append("customer", body.customer_id);
        params.append("return_url", body.return_url || "https://mcpfw.relayshield.net/");

        const res = await fetch("https://api.stripe.com/v1/billing_portal/sessions", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: params.toString(),
        });

        const session = await res.json();
        if (session.error) {
          return error(session.error.message, 400);
        }

        return json({ portal_url: session.url });
      } catch (e) {
        console.error("Stripe portal error:", e);
        return error("Failed to create portal session", 502);
      }
    }

    return error("Unknown billing action");
  }

  return error("Method not allowed", 405);
}

// --- Overview (aggregated dashboard data) ---
// --- ROI: map a screening.blocked audit entry to a threat category ---
// Categories: malicious_domain, phishing_kit, malware_indicator,
// prompt_injection, data_exfiltration, path_traversal, ssrf, other
function roiCategory(entry) {
  const d = (entry && entry.details) || {};
  if (typeof d.threat_category === "string" && d.threat_category) return d.threat_category;
  const src = String(d.confidence_source || "").toLowerCase();
  if (src === "path_traversal") return "path_traversal";
  if (src === "ssrf") return "ssrf";
  const reason = String(d.reason || "").toLowerCase();
  if (reason.includes("phishing") || reason.includes("kit_")) return "phishing_kit";
  if (reason.includes("injection")) return "prompt_injection";
  if (reason.includes("exfiltrat")) return "data_exfiltration";
  if (reason.includes("malware")) return "malware_indicator";
  if (src === "threat_intel") return "malicious_domain";
  return "other";
}

// --- ROI: bucket events into labeled time buckets ---
function roiBucketize(events, startMs, endMs, bucketMs, labelFn) {
  const buckets = [];
  const n = Math.ceil((endMs - startMs) / bucketMs);
  for (let i = 0; i < n; i++) {
    const bs = startMs + i * bucketMs;
    const be = Math.min(bs + bucketMs, endMs);
    buckets.push({ start: bs, end: be, label: labelFn(bs, be), count: 0 });
  }
  for (const e of events) {
    const ts = new Date(e.timestamp).getTime();
    if (isNaN(ts) || ts < startMs || ts >= endMs) continue;
    const idx = Math.min(Math.floor((ts - startMs) / bucketMs), buckets.length - 1);
    buckets[idx].count++;
  }
  return buckets.map(b => ({ label: b.label, count: b.count }));
}

function roiShortDate(ts) {
  const d = new Date(ts);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return months[d.getMonth()] + " " + d.getDate();
}

// Conservative assumed cost avoidance per blocked threat (USD).
// Deliberately below the $264K NetDiligence 2025 SMB average incident cost
// because not every blocked call would have become a full incident.
const ROI_COST_PER_INCIDENT = 50000;

async function handleOverview(request, env, ctx) {
  if (request.method === "GET") {
    const url = new URL(request.url);
    const range = url.searchParams.get("range") || "24h"; // 24h, 7d, 30d

    const groups = await env.CONFIG_KV.get("server_groups", "json") || [];
    const quarantine = await env.CONFIG_KV.get("quarantine", "json") || [];

    // Confidence aggregates from audit log (last 24h, events with details.confidence)
    let confidenceStats = {
      total_verdicts_24h: 0,
      avg_confidence_24h: null,
      low_confidence_count_24h: 0,
      confidence_histogram_24h: { "0.9_1.0": 0, "0.7_0.9": 0, "0.5_0.7": 0, "below_0.5": 0 },
      // Per-server breakdown: { "server-id": { total_verdicts, avg_confidence, low_confidence_count } }
      confidence_by_server: {},
    };
    try {
      const auditEntries = await env.AUDIT_KV.get("audit_log", "json") || [];
      const cutoff = Date.now() - 24 * 60 * 60 * 1000;
      const verdicts = auditEntries.filter(e => {
        const ts = new Date(e.timestamp).getTime();
        return ts >= cutoff && e.details && typeof e.details.confidence === "number";
      });
      if (verdicts.length) {
        const sum = verdicts.reduce((s, e) => s + e.details.confidence, 0);
        confidenceStats.total_verdicts_24h = verdicts.length;
        confidenceStats.avg_confidence_24h = Math.round((sum / verdicts.length) * 100) / 100;
        confidenceStats.low_confidence_count_24h = verdicts.filter(e => e.details.confidence < 0.6).length;
        for (const e of verdicts) {
          const c = e.details.confidence;
          if (c >= 0.9) confidenceStats.confidence_histogram_24h["0.9_1.0"]++;
          else if (c >= 0.7) confidenceStats.confidence_histogram_24h["0.7_0.9"]++;
          else if (c >= 0.5) confidenceStats.confidence_histogram_24h["0.5_0.7"]++;
          else confidenceStats.confidence_histogram_24h["below_0.5"]++;
        }
        // Per-server breakdown
        const byServer = {};
        for (const e of verdicts) {
          const sid = e.details.server_id || "unknown";
          if (!byServer[sid]) byServer[sid] = { total: 0, sum: 0, low: 0 };
          byServer[sid].total++;
          byServer[sid].sum += e.details.confidence;
          if (e.details.confidence < 0.6) byServer[sid].low++;
        }
        for (const sid of Object.keys(byServer)) {
          const b = byServer[sid];
          confidenceStats.confidence_by_server[sid] = {
            total_verdicts: b.total,
            avg_confidence: Math.round((b.sum / b.total) * 100) / 100,
            low_confidence_count: b.low,
          };
        }
      }
    } catch (e) {
      console.error("Confidence aggregation failed:", e);
    }

    // ROI aggregates: screening.blocked events -> estimated cost avoidance.
    // blocked_30d / blocked_ytd / blocked_12m, per-category breakdowns, and
    // weekly/monthly bucket series for the ROI chart.
    let roi = {
      blocked_30d: 0,
      blocked_ytd: 0,
      blocked_12m: 0,
      by_category_30d: {},
      by_category_ytd: {},
      by_category_12m: {},
      cost_per_incident: ROI_COST_PER_INCIDENT,
      savings_30d: 0,
      savings_ytd: 0,
      savings_12m: 0,
      weekly_30d: [],
      weekly_ytd: [],
      weekly_12m: [],
    };
    try {
      const auditEntries = await env.AUDIT_KV.get("audit_log", "json") || [];
      const now = Date.now();
      const cutoff30d = now - 30 * 24 * 60 * 60 * 1000;
      const cutoff12m = now - 365 * 24 * 60 * 60 * 1000;
      const ytdStart = new Date(new Date().getFullYear(), 0, 1).getTime();
      const inWindow = (e, cutoff) => {
        const ts = new Date(e.timestamp).getTime();
        return !isNaN(ts) && ts >= cutoff && ts <= now;
      };
      const blocked = auditEntries.filter(e => e.event_type === "screening.blocked" && inWindow(e, cutoff12m));
      const b30 = blocked.filter(e => inWindow(e, cutoff30d));
      const bytd = blocked.filter(e => inWindow(e, ytdStart));
      roi.blocked_30d = b30.length;
      roi.blocked_ytd = bytd.length;
      roi.blocked_12m = blocked.length;
      roi.savings_30d = b30.length * ROI_COST_PER_INCIDENT;
      roi.savings_ytd = bytd.length * ROI_COST_PER_INCIDENT;
      roi.savings_12m = blocked.length * ROI_COST_PER_INCIDENT;
      for (const e of b30) {
        const c = roiCategory(e);
        roi.by_category_30d[c] = (roi.by_category_30d[c] || 0) + 1;
      }
      for (const e of bytd) {
        const c = roiCategory(e);
        roi.by_category_ytd[c] = (roi.by_category_ytd[c] || 0) + 1;
      }
      for (const e of blocked) {
        const c = roiCategory(e);
        roi.by_category_12m[c] = (roi.by_category_12m[c] || 0) + 1;
      }
      const week = 7 * 24 * 60 * 60 * 1000;
      roi.weekly_30d = roiBucketize(b30, cutoff30d, now, week, (s) => roiShortDate(s));
      // YTD and 12m bucketed by calendar month for readability.
      const monthBuckets = (events, startMs) => {
        const out = [];
        const cursor = new Date(startMs);
        cursor.setDate(1);
        cursor.setHours(0, 0, 0, 0);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        while (cursor.getTime() < now) {
          const ms = cursor.getTime();
          const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1).getTime();
          const count = events.filter(e => {
            const ts = new Date(e.timestamp).getTime();
            return !isNaN(ts) && ts >= ms && ts < Math.min(next, now);
          }).length;
          out.push({ label: months[cursor.getMonth()] + " '" + String(cursor.getFullYear()).slice(2), count });
          cursor.setMonth(cursor.getMonth() + 1);
        }
        return out;
      };
      roi.weekly_ytd = monthBuckets(bytd, ytdStart);
      roi.weekly_12m = monthBuckets(blocked, cutoff12m);
    } catch (e) {
      console.error("ROI aggregation failed:", e);
    }

    // TODO: Aggregate real metrics from proxy logs
    return json({
      range,
      summary: {
        total_servers: groups.reduce((n, g) => n + (g.servers?.length || 0), 0),
        healthy: 0, // TODO: real counts
        degraded: 0,
        quarantined: quarantine.length,
        total_requests: 0, // TODO
        blocked_requests: 0, // TODO
      },
      confidence: confidenceStats,
      roi,
      groups: groups.map(g => ({
        id: g.id,
        name: g.name,
        server_count: g.servers?.length || 0,
        avg_reputation: g.servers?.length
          ? Math.round(g.servers.reduce((s, srv) => s + (srv.reputation || 0), 0) / g.servers.length)
          : 0,
      })),
      note: "Metrics are placeholders until proxy telemetry is connected",
    });
  }

  return error("Method not allowed", 405);
}

// --- Main router ---
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: JSON_HEADERS });
    }

    // API routes
    if (url.pathname.startsWith("/api/")) {
      const auth = await getAuth(request, env);

      if (url.pathname === "/api/overview") return handleOverview(request, env, ctx);
      if (url.pathname === "/api/servers") return handleServers(request, env, ctx);
      if (url.pathname === "/api/policies") return handlePolicies(request, env, ctx);
      if (url.pathname === "/api/quarantine") return handleQuarantine(request, env, ctx);
      if (url.pathname === "/api/audit") return handleAudit(request, env, ctx);
      if (url.pathname === "/api/telemetry") return handleTelemetry(request, env, ctx);
      if (url.pathname.startsWith("/api/keys")) return handleKeys(request, env, ctx);
      if (url.pathname === "/api/verifiers") return handleVerifiers(request, env, ctx);
      if (url.pathname === "/api/billing") return handleBilling(request, env, ctx);

      return error("API endpoint not found", 404);
    }

    // Serve console UI for all other paths
    // The HTML is inlined at build time (see build script)
    return new Response(CONSOLE_HTML, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  },
};

// CONSOLE_HTML is injected by the build script
const CONSOLE_HTML = `__CONSOLE_HTML_PLACEHOLDER__`;
