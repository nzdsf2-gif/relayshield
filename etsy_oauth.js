// ETSY-OAUTH-PKCE-2026-11-22
// RelayShield Etsy app: OAuth 2.0 Authorization Code Grant with PKCE.
// Connects a seller's Etsy shop to a RelayShield account.
//
// Host: the landing Worker (relayshield.net). The callback URL must be
// https://relayshield.net/etsy/oauth/callback, and relayshield.net is served
// only by the landing Worker (cloudflare_worker_landing.js). The API Gateway
// (api.relayshield.net) cannot serve a relayshield.net URL, so the callback
// handler lives in the landing Worker as a route. This module is written as
// an ES module so it can be imported by the landing Worker. It uses only
// Web Crypto (crypto.subtle, crypto.getRandomValues) and fetch, which are
// available in Cloudflare Workers and in Node 18+.
//
// Flow:
//   1. Seller clicks Connect Etsy. handleEtsyStart generates a state token and
//      a PKCE code verifier, stores them as a pending authorization, and
//      redirects the seller to https://www.etsy.com/oauth/connect.
//   2. The seller approves the scopes on Etsy. Etsy redirects back to the
//      callback with a code and the state.
//   3. handleEtsyCallback validates the state (single-use, expires after
//      10 minutes), exchanges the code for tokens, resolves the shop, and
//      stores the tokens in DynamoDB keyed by shop_id.
//   4. Later API calls use getValidAccessToken, which returns a valid access
//      token and refreshes it with the refresh token before it expires.
//      When the refresh token itself has expired (90 days), the record is
//      marked reauth_required and the seller must reconnect.
//
// Scopes (read-only v1, exactly these four): shops_r, listings_r,
// transactions_r, email_r. Write scopes and buyer_email are NOT requested.
//
// Credentials: the Etsy app keystring (client ID) and shared secret (client
// secret) are NOT in this file. They are read from the Worker environment
// (ETSY_CLIENT_ID, ETSY_CLIENT_SECRET) and are filled in after Andrew
// creates the Personal App in Etsy. No credentials are invented here.
//
// Token storage: DynamoDB table relayshield_etsy_tokens, partition key pk.
// A token record is stored under pk = shop_id. A pending authorization is
// stored under pk = "pending:" + state with a TTL so it expires. The table
// must be provisioned (PAY_PER_REQUEST, TTL enabled on the "ttl" attribute)
// on Andrew's go. Tokens are never logged and never returned to the browser.
//
// This module is not deployed and the Etsy app is not registered. Nothing
// here claims the app is live or approved.

export const ETSY_AUTH_URL = "https://www.etsy.com/oauth/connect";
export const ETSY_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token";
export const ETSY_API_BASE = "https://api.etsy.com/v3/application";
export const REDIRECT_URI = "https://relayshield.net/etsy/oauth/callback";
export const ETSY_SCOPES = ["shops_r", "listings_r", "transactions_r", "email_r"];
export const ACCESS_TOKEN_TTL_SECONDS = 3600;
export const REFRESH_TOKEN_TTL_SECONDS = 90 * 24 * 3600;
export const PENDING_TTL_SECONDS = 600;
export const CLOCK_SKEW_SECONDS = 60;
export const DEFAULT_TOKEN_TABLE = "relayshield_etsy_tokens";
export const DEFAULT_AWS_REGION = "us-east-1";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

// Read the Etsy OAuth configuration from the Worker environment. Throws a
// clear error naming the missing variable. ETSY_CLIENT_ID is the Etsy app
// keystring. ETSY_CLIENT_SECRET is the Etsy app shared secret. Both are
// set after the Personal App is created in Etsy. ETSY_TOKEN_TABLE and
// AWS_REGION have defaults. AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are
// the IAM credentials the Worker uses to sign DynamoDB requests (the same
// pattern the console Worker uses).
export function readEtsyConfig(env) {
  const source = env || {};
  const missing = [];
  if (!source.ETSY_CLIENT_ID) missing.push("ETSY_CLIENT_ID");
  if (!source.ETSY_CLIENT_SECRET) missing.push("ETSY_CLIENT_SECRET");
  if (!source.AWS_ACCESS_KEY_ID) missing.push("AWS_ACCESS_KEY_ID");
  if (!source.AWS_SECRET_ACCESS_KEY) missing.push("AWS_SECRET_ACCESS_KEY");
  if (missing.length > 0) {
    throw new Error("missing Etsy OAuth config: " + missing.join(", "));
  }
  return {
    clientId: source.ETSY_CLIENT_ID,
    clientSecret: source.ETSY_CLIENT_SECRET,
    tableName: source.ETSY_TOKEN_TABLE || DEFAULT_TOKEN_TABLE,
    awsRegion: source.AWS_REGION || DEFAULT_AWS_REGION,
    awsAccessKeyId: source.AWS_ACCESS_KEY_ID,
    awsSecretAccessKey: source.AWS_SECRET_ACCESS_KEY,
  };
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

export function base64urlEncode(bytes) {
  let binary = "";
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (let i = 0; i < arr.length; i++) {
    binary += String.fromCharCode(arr[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function defaultRandomBytes(length) {
  const arr = new Uint8Array(length);
  globalThis.crypto.getRandomValues(arr);
  return arr;
}

function defaultNowSeconds() {
  return Math.floor(Date.now() / 1000);
}

// ---------------------------------------------------------------------------
// PKCE and state
// ---------------------------------------------------------------------------

// Generate a PKCE code verifier: 32 random bytes, base64url encoded, 43
// characters from [A-Za-z0-9._~-]. Etsy requires 43 to 128 characters.
export function generateCodeVerifier(randomBytesFn) {
  const random = randomBytesFn || defaultRandomBytes;
  return base64urlEncode(random(32));
}

// Generate the S256 code challenge: base64url(SHA-256(verifier)). Async
// because crypto.subtle.digest is async.
export async function generateCodeChallenge(verifier) {
  const data = new TextEncoder().encode(verifier);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", data);
  return base64urlEncode(new Uint8Array(digest));
}

// Generate a single-use state token: 32 random bytes, base64url encoded.
// Unguessable (256 bits of entropy). Stored server-side with the verifier
// and consumed exactly once at the callback.
export function generateState(randomBytesFn) {
  const random = randomBytesFn || defaultRandomBytes;
  return base64urlEncode(random(32));
}

// ---------------------------------------------------------------------------
// Authorization URL
// ---------------------------------------------------------------------------

// Build the Etsy authorization URL. The redirect_uri must exactly match the
// callback URL registered in the Etsy app. Scopes are the four read-only v1
// scopes. code_challenge_method is always S256.
export function buildAuthorizationUrl(params) {
  const query = [
    "response_type=" + encodeURIComponent("code"),
    "client_id=" + encodeURIComponent(params.clientId),
    "redirect_uri=" + encodeURIComponent(params.redirectUri || REDIRECT_URI),
    "scope=" + encodeURIComponent((params.scopes || ETSY_SCOPES).join(" ")),
    "state=" + encodeURIComponent(params.state),
    "code_challenge=" + encodeURIComponent(params.codeChallenge),
    "code_challenge_method=" + encodeURIComponent("S256"),
  ].join("&");
  return ETSY_AUTH_URL + "?" + query;
}

// ---------------------------------------------------------------------------
// Token response parsing
// ---------------------------------------------------------------------------

// Extract the Etsy user id from an access or refresh token. Etsy tokens
// carry a numeric user id prefix, for example "12345678.abcdef". Returns
// the numeric prefix as a string, or null when the token has no such prefix.
export function extractUserIdFromToken(token) {
  if (typeof token !== "string") return null;
  const prefix = token.split(".")[0];
  if (/^\d+$/.test(prefix)) return prefix;
  return null;
}

// Parse an Etsy token response (authorization code grant or refresh grant)
// into a normalized record. accessExpiresAt is now plus expires_in (3600
// seconds, 1 hour). refreshExpiresAt is now plus 90 days. Throws when the
// response is missing an access token or a refresh token.
export function parseTokenResponse(json, nowSeconds) {
  const now = typeof nowSeconds === "number" ? nowSeconds : defaultNowSeconds();
  if (!json || typeof json !== "object") {
    throw new Error("invalid token response: not an object");
  }
  if (!json.access_token || typeof json.access_token !== "string") {
    throw new Error("invalid token response: missing access_token");
  }
  if (!json.refresh_token || typeof json.refresh_token !== "string") {
    throw new Error("invalid token response: missing refresh_token");
  }
  const expiresIn = typeof json.expires_in === "number" ? json.expires_in : ACCESS_TOKEN_TTL_SECONDS;
  const scope = typeof json.scope === "string" ? json.scope : "";
  return {
    accessToken: json.access_token,
    refreshToken: json.refresh_token,
    tokenType: json.token_type || "Bearer",
    expiresIn: expiresIn,
    scope: scope,
    scopeList: scope.length > 0 ? scope.split(" ") : [],
    accessExpiresAt: now + expiresIn,
    refreshExpiresAt: now + REFRESH_TOKEN_TTL_SECONDS,
    etsyUserId: extractUserIdFromToken(json.access_token),
  };
}

// ---------------------------------------------------------------------------
// Token endpoint calls
// ---------------------------------------------------------------------------

function formBody(params) {
  const parts = [];
  for (const key of Object.keys(params)) {
    parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
  }
  return parts.join("&");
}

async function postTokenEndpoint(body, fetchFn) {
  const doFetch = fetchFn || globalThis.fetch;
  const res = await doFetch(ETSY_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body,
  });
  const text = await res.text();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch (e) {
    json = null;
  }
  if (!res.ok) {
    const detail = json && json.error ? String(json.error) : "HTTP " + res.status;
    const err = new Error("Etsy token request failed: " + detail);
    if (json && json.error === "invalid_grant") err.code = "invalid_grant";
    err.status = res.status;
    throw err;
  }
  if (!json) {
    throw new Error("Etsy token request failed: response was not JSON");
  }
  return json;
}

// Exchange an authorization code for tokens. Sends grant_type,
// authorization_code, client_id, redirect_uri, code, and code_verifier.
// The redirect_uri must match the value used at the authorization endpoint.
export async function exchangeCodeForTokens(params) {
  const body = formBody({
    grant_type: "authorization_code",
    client_id: params.config.clientId,
    redirect_uri: params.redirectUri || REDIRECT_URI,
    code: params.code,
    code_verifier: params.codeVerifier,
  });
  return postTokenEndpoint(body, params.fetchFn);
}

// Refresh an access token with a refresh token. Sends grant_type
// refresh_token, client_id, and refresh_token. Etsy rotates the refresh
// token: the response carries a new refresh_token to store.
export async function refreshAccessToken(params) {
  const body = formBody({
    grant_type: "refresh_token",
    client_id: params.config.clientId,
    refresh_token: params.refreshToken,
  });
  return postTokenEndpoint(body, params.fetchFn);
}

// ---------------------------------------------------------------------------
// Etsy API calls (shop and user lookup)
// ---------------------------------------------------------------------------

// Resolve the seller's shop id. Calls GET /users/{userId}/shops with the
// x-api-key header (keystring and shared secret separated by a colon) and
// the Bearer access token. Returns the first shop id, or null when the
// user has no shops. Throws on an HTTP error so the caller can show a
// retry-able error. v1 serves one shop per tenant; when a seller has
// several shops, v1 takes the first and records the full list.
export async function resolveShopId(params) {
  const userId = extractUserIdFromToken(params.accessToken);
  if (!userId) return null;
  const doFetch = params.fetchFn || globalThis.fetch;
  const url = ETSY_API_BASE + "/users/" + encodeURIComponent(userId) + "/shops";
  const res = await doFetch(url, {
    method: "GET",
    headers: {
      "x-api-key": params.config.clientId + ":" + params.config.clientSecret,
      Authorization: "Bearer " + params.accessToken,
    },
  });
  if (!res.ok) {
    throw new Error("Etsy shop lookup failed: HTTP " + res.status);
  }
  const json = await res.json();
  const results = json && Array.isArray(json.results) ? json.results : [];
  if (results.length === 0) return null;
  return {
    shopId: String(results[0].shop_id),
    shopIds: results.map(function (s) { return String(s.shop_id); }),
    shopName: results[0].shop_name || null,
  };
}

// Fetch the Etsy user's email address (scope email_r) for linking the Etsy
// account to a RelayShield account. Best effort: returns the email string
// or null when the call fails or the field is absent. Never throws.
export async function fetchEtsyUserEmail(params) {
  try {
    const userId = extractUserIdFromToken(params.accessToken);
    if (!userId) return null;
    const doFetch = params.fetchFn || globalThis.fetch;
    const url = ETSY_API_BASE + "/users/" + encodeURIComponent(userId);
    const res = await doFetch(url, {
      method: "GET",
      headers: {
        "x-api-key": params.config.clientId + ":" + params.config.clientSecret,
        Authorization: "Bearer " + params.accessToken,
      },
    });
    if (!res.ok) return null;
    const json = await res.json();
    if (json && typeof json.primary_email === "string") return json.primary_email;
    return null;
  } catch (e) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Token record and expiry
// ---------------------------------------------------------------------------

// Build the token record stored in DynamoDB, keyed by shop_id. Expiry
// times are epoch seconds. reauth_required starts false. The record never
// leaves the server: it is not returned to the browser.
export function buildTokenRecord(params) {
  const now = typeof params.nowSeconds === "number" ? params.nowSeconds : defaultNowSeconds();
  return {
    pk: params.shopId,
    shop_id: params.shopId,
    etsy_user_id: params.tokens.etsyUserId,
    etsy_email: params.etsyEmail || null,
    shop_name: params.shopName || null,
    shop_ids: params.shopIds || [params.shopId],
    access_token: params.tokens.accessToken,
    refresh_token: params.tokens.refreshToken,
    token_type: params.tokens.tokenType,
    access_expires_at: params.tokens.accessExpiresAt,
    refresh_expires_at: params.tokens.refreshExpiresAt,
    scopes: params.tokens.scope,
    reauth_required: false,
    connected_at: now,
    updated_at: now,
  };
}

// True when the access token is expired or within the clock-skew margin
// of expiring. The margin avoids using a token that expires mid-request.
export function isAccessTokenExpired(record, nowSeconds, skewSeconds) {
  const now = typeof nowSeconds === "number" ? nowSeconds : defaultNowSeconds();
  const skew = typeof skewSeconds === "number" ? skewSeconds : CLOCK_SKEW_SECONDS;
  return now >= record.access_expires_at - skew;
}

// True when the refresh token itself has expired (90 days after issue).
// A refresh token cannot be renewed; the seller must reconnect.
export function isRefreshTokenExpired(record, nowSeconds) {
  const now = typeof nowSeconds === "number" ? nowSeconds : defaultNowSeconds();
  return now >= record.refresh_expires_at;
}

export class ReauthRequiredError extends Error {
  constructor(message) {
    super(message || "Etsy re-authorization required: the refresh token has expired or was revoked. The seller must reconnect the shop.");
    this.name = "ReauthRequiredError";
    this.code = "reauth_required";
  }
}

// Return a valid access token for a shop, refreshing it when needed.
//   - No record: throws an Error naming the shop, so the caller prompts
//     the seller to connect.
//   - Access token still valid: returns it without a network call.
//   - Access token expired but refresh token valid: refreshes, stores the
//     new tokens (rotating the refresh token when Etsy issues a new one),
//     and returns the new access token.
//   - Refresh token expired or revoked (invalid_grant): marks the record
//     reauth_required and throws ReauthRequiredError. The caller surfaces
//     a re-connect prompt; it does not silently fail.
//   - Transient refresh failure (network, 5xx): does NOT mark
//     reauth_required. Throws the error so the caller can retry.
export async function getValidAccessToken(params) {
  const now = typeof params.nowSeconds === "number" ? params.nowSeconds : defaultNowSeconds();
  const record = await params.store.get(params.shopId);
  if (!record) {
    throw new Error("no Etsy token record for shop " + params.shopId + ": the seller must connect the shop");
  }
  if (record.reauth_required) {
    throw new ReauthRequiredError();
  }
  if (!isAccessTokenExpired(record, now)) {
    return { accessToken: record.access_token, record: record };
  }
  if (isRefreshTokenExpired(record, now)) {
    await params.store.update(params.shopId, { reauth_required: true, updated_at: now });
    throw new ReauthRequiredError();
  }
  let json;
  try {
    json = await refreshAccessToken({
      refreshToken: record.refresh_token,
      config: params.config,
      fetchFn: params.fetchFn,
    });
  } catch (e) {
    if (e && e.code === "invalid_grant") {
      await params.store.update(params.shopId, { reauth_required: true, updated_at: now });
      throw new ReauthRequiredError("Etsy refresh token was revoked. The seller must reconnect the shop.");
    }
    throw e;
  }
  const tokens = parseTokenResponse(json, now);
  const updates = {
    access_token: tokens.accessToken,
    access_expires_at: tokens.accessExpiresAt,
    updated_at: now,
  };
  if (tokens.refreshToken && tokens.refreshToken !== record.refresh_token) {
    updates.refresh_token = tokens.refreshToken;
    updates.refresh_expires_at = tokens.refreshExpiresAt;
  }
  if (tokens.scope) updates.scopes = tokens.scope;
  await params.store.update(params.shopId, updates);
  const updated = await params.store.get(params.shopId);
  return { accessToken: tokens.accessToken, record: updated || record };
}

// ---------------------------------------------------------------------------
// Pending authorizations (state + code verifier, single-use, 10 minutes)
// ---------------------------------------------------------------------------

function pendingPk(state) {
  return "pending:" + state;
}

// Store a pending authorization: state maps to the code verifier. The
// record expires after PENDING_TTL_SECONDS (10 minutes) via the ttl
// attribute, so a stale state cannot be replayed later.
export async function savePendingAuth(params) {
  const now = typeof params.nowSeconds === "number" ? params.nowSeconds : defaultNowSeconds();
  await params.store.put(pendingPk(params.state), {
    pk: pendingPk(params.state),
    code_verifier: params.codeVerifier,
    account_hint: params.accountHint || null,
    created_at: now,
    ttl: now + PENDING_TTL_SECONDS,
  });
}

// Consume a pending authorization exactly once. Returns the code verifier
// when the state exists and has not expired, and deletes the record so
// the state cannot be reused. Returns null for an unknown, expired, or
// already-consumed state. An expired record is deleted when found.
export async function consumePendingAuth(params) {
  const now = typeof params.nowSeconds === "number" ? params.nowSeconds : defaultNowSeconds();
  const record = await params.store.get(pendingPk(params.state));
  if (!record) return null;
  await params.store.delete(pendingPk(params.state));
  if (record.ttl && now >= record.ttl) return null;
  return { codeVerifier: record.code_verifier, accountHint: record.account_hint || null };
}

// ---------------------------------------------------------------------------
// DynamoDB store (SigV4 signed, same pattern as the console Worker)
// ---------------------------------------------------------------------------

function sha256Hex(data) {
  return globalThis.crypto.subtle.digest("SHA-256", data).then(function (digest) {
    const bytes = new Uint8Array(digest);
    let hex = "";
    for (let i = 0; i < bytes.length; i++) {
      hex += bytes[i].toString(16).padStart(2, "0");
    }
    return hex;
  });
}

async function hmacSha256(keyBytes, dataBytes) {
  const key = await globalThis.crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await globalThis.crypto.subtle.sign("HMAC", key, dataBytes);
  return new Uint8Array(sig);
}

function bytesToHex(bytes) {
  let hex = "";
  for (let i = 0; i < bytes.length; i++) {
    hex += bytes[i].toString(16).padStart(2, "0");
  }
  return hex;
}

// Sign a DynamoDB request with AWS Signature Version 4. Returns the
// Authorization header value. Follows the same signing pattern the console
// Worker uses for DynamoDB (SigV4, service dynamodb, region from config).
export async function signDynamoRequest(params) {
  const region = params.config.awsRegion;
  const service = "dynamodb";
  const amzDate = params.amzDate;
  const dateStamp = amzDate.slice(0, 8);
  const scope = dateStamp + "/" + region + "/" + service + "/aws4_request";
  const host = "dynamodb." + region + ".amazonaws.com";
  const payloadHash = await sha256Hex(new TextEncoder().encode(params.body));
  const canonicalHeaders =
    "content-type:application/x-amz-json-1.0\n" +
    "host:" + host + "\n" +
    "x-amz-date:" + amzDate + "\n" +
    "x-amz-target:DynamoDB_20120810." + params.action + "\n";
  const signedHeaders = "content-type;host;x-amz-date;x-amz-target";
  const canonicalRequest = [
    "POST",
    "/",
    "",
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");
  const canonicalRequestHash = await sha256Hex(new TextEncoder().encode(canonicalRequest));
  const stringToSign = ["AWS4-HMAC-SHA256", amzDate, scope, canonicalRequestHash].join("\n");
  const encoder = new TextEncoder();
  const kDate = await hmacSha256(encoder.encode("AWS4" + params.config.awsSecretAccessKey), encoder.encode(dateStamp));
  const kRegion = await hmacSha256(kDate, encoder.encode(region));
  const kService = await hmacSha256(kRegion, encoder.encode(service));
  const kSigning = await hmacSha256(kService, encoder.encode("aws4_request"));
  const signature = bytesToHex(await hmacSha256(kSigning, encoder.encode(stringToSign)));
  return "AWS4-HMAC-SHA256 Credential=" + params.config.awsAccessKeyId + "/" + scope +
    ", SignedHeaders=" + signedHeaders + ", Signature=" + signature;
}

function marshalValue(value) {
  if (typeof value === "string") return { S: value };
  if (typeof value === "number") return { N: String(value) };
  if (typeof value === "boolean") return { BOOL: value };
  if (value === null || value === undefined) return { NULL: true };
  if (Array.isArray(value)) return { L: value.map(marshalValue) };
  return { S: JSON.stringify(value) };
}

function unmarshalValue(attr) {
  if (!attr || typeof attr !== "object") return null;
  if (typeof attr.S === "string") return attr.S;
  if (typeof attr.N === "string") return Number(attr.N);
  if (typeof attr.BOOL === "boolean") return attr.BOOL;
  if (attr.NULL) return null;
  if (Array.isArray(attr.L)) return attr.L.map(unmarshalValue);
  return null;
}

function marshalItem(obj) {
  const item = {};
  for (const key of Object.keys(obj)) {
    item[key] = marshalValue(obj[key]);
  }
  return item;
}

function unmarshalItem(item) {
  if (!item) return null;
  const obj = {};
  for (const key of Object.keys(item)) {
    obj[key] = unmarshalValue(item[key]);
  }
  return obj;
}

// A DynamoDB-backed store implementing the put/get/delete/update interface
// the flow functions use. Plain JS objects go in and out; marshalling to
// DynamoDB JSON happens here. Create one per request from the config.
export function createDynamoStore(config, fetchFn) {
  const doFetch = fetchFn || globalThis.fetch;
  async function call(action, payload, nowSeconds) {
    const now = typeof nowSeconds === "number" ? nowSeconds : defaultNowSeconds();
    const date = new Date(now * 1000);
    const amzDate = date.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
    const body = JSON.stringify(payload);
    const authorization = await signDynamoRequest({ config: config, action: action, body: body, amzDate: amzDate });
    const url = "https://dynamodb." + config.awsRegion + ".amazonaws.com/";
    const res = await doFetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": "DynamoDB_20120810." + action,
        "X-Amz-Date": amzDate,
        Authorization: authorization,
      },
      body: body,
    });
    const text = await res.text();
    if (!res.ok) {
      throw new Error("DynamoDB " + action + " failed: HTTP " + res.status + ": " + text.slice(0, 200));
    }
    return text ? JSON.parse(text) : {};
  }
  return {
    async put(pk, obj) {
      const item = Object.assign({}, obj, { pk: pk });
      await call("PutItem", { TableName: config.tableName, Item: marshalItem(item) });
    },
    async get(pk) {
      const out = await call("GetItem", {
        TableName: config.tableName,
        Key: { pk: { S: pk } },
        ConsistentRead: true,
      });
      return unmarshalItem(out.Item);
    },
    async delete(pk) {
      await call("DeleteItem", { TableName: config.tableName, Key: { pk: { S: pk } } });
    },
    async update(pk, fields) {
      const names = {};
      const values = {};
      const sets = [];
      let i = 0;
      for (const key of Object.keys(fields)) {
        const nameKey = "#k" + i;
        const valueKey = ":v" + i;
        names[nameKey] = key;
        values[valueKey] = marshalValue(fields[key]);
        sets.push(nameKey + " = " + valueKey);
        i++;
      }
      if (sets.length === 0) return;
      await call("UpdateItem", {
        TableName: config.tableName,
        Key: { pk: { S: pk } },
        UpdateExpression: "SET " + sets.join(", "),
        ExpressionAttributeNames: names,
        ExpressionAttributeValues: values,
      });
    },
  };
}

// ---------------------------------------------------------------------------
// Route handlers (wired into the landing Worker)
// ---------------------------------------------------------------------------

function htmlPage(title, body) {
  return "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" +
    "<title>" + title + " - RelayShield</title></head>" +
    "<body style=\"font-family: sans-serif; max-width: 640px; margin: 48px auto; padding: 0 24px; line-height: 1.6;\">" +
    body + "</body></html>";
}

function errorResponse(title, message, status) {
  const body = "<h1>" + title + "</h1><p>" + message + "</p>" +
    "<p><a href=\"https://relayshield.net/\">Back to RelayShield</a></p>";
  return new Response(htmlPage(title, body), {
    status: status || 400,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

// Start the connect flow. Generates state and a PKCE verifier, stores them
// as a pending authorization, and redirects the seller to Etsy to approve
// the four read-only scopes. Called from GET /etsy/oauth/start.
export async function handleEtsyStart(request, env, deps) {
  const d = deps || {};
  const config = readEtsyConfig(env);
  const store = d.store || createDynamoStore(config, d.fetchFn);
  const randomBytesFn = d.randomBytesFn;
  const now = typeof d.nowSeconds === "number" ? d.nowSeconds : defaultNowSeconds();
  const state = generateState(randomBytesFn);
  const codeVerifier = generateCodeVerifier(randomBytesFn);
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const url = new URL(request.url);
  const accountHint = url.searchParams.get("account") || null;
  await savePendingAuth({ store: store, state: state, codeVerifier: codeVerifier, accountHint: accountHint, nowSeconds: now });
  const authUrl = buildAuthorizationUrl({
    clientId: config.clientId,
    redirectUri: REDIRECT_URI,
    scopes: ETSY_SCOPES,
    state: state,
    codeChallenge: codeChallenge,
  });
  return Response.redirect(authUrl, 302);
}

// Handle the Etsy redirect back to https://relayshield.net/etsy/oauth/callback.
// Validates the state, exchanges the code for tokens, resolves the shop,
// stores the tokens keyed by shop_id, and returns a success page. On any
// failure it returns an error page and stores nothing. Tokens are never
// included in the response.
export async function handleEtsyCallback(request, env, deps) {
  const d = deps || {};
  const config = readEtsyConfig(env);
  const store = d.store || createDynamoStore(config, d.fetchFn);
  const fetchFn = d.fetchFn;
  const now = typeof d.nowSeconds === "number" ? d.nowSeconds : defaultNowSeconds();
  const url = new URL(request.url);
  const error = url.searchParams.get("error");
  if (error) {
    const detail = url.searchParams.get("error_description") || "Etsy returned an error and did not grant access.";
    return errorResponse("Etsy connection failed", "Etsy did not grant access: " + detail + " Please try connecting again.", 400);
  }
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code || !state) {
    return errorResponse("Etsy connection failed", "The callback from Etsy was missing the authorization code or state. Please try connecting again.", 400);
  }
  const pending = await consumePendingAuth({ store: store, state: state, nowSeconds: now });
  if (!pending) {
    return errorResponse("Etsy connection failed", "The connection request expired or was already used. Please start the Etsy connection again.", 400);
  }
  let tokenJson;
  try {
    tokenJson = await exchangeCodeForTokens({
      code: code,
      codeVerifier: pending.codeVerifier,
      config: config,
      redirectUri: REDIRECT_URI,
      fetchFn: fetchFn,
    });
  } catch (e) {
    return errorResponse("Etsy connection failed", "The token exchange with Etsy failed. Please try connecting again.", 502);
  }
  let tokens;
  try {
    tokens = parseTokenResponse(tokenJson, now);
  } catch (e) {
    return errorResponse("Etsy connection failed", "Etsy returned a token response the app could not read. Please try connecting again.", 502);
  }
  let shop;
  try {
    shop = await resolveShopId({ accessToken: tokens.accessToken, config: config, fetchFn: fetchFn });
  } catch (e) {
    return errorResponse("Etsy connection failed", "The app could not read the shop for this Etsy account. Please try connecting again.", 502);
  }
  if (!shop) {
    return errorResponse("Etsy connection failed", "No shop was found on this Etsy account. The RelayShield Etsy app needs a shop to connect. Create a shop on Etsy first, then connect again.", 400);
  }
  const etsyEmail = await fetchEtsyUserEmail({ accessToken: tokens.accessToken, config: config, fetchFn: fetchFn });
  const record = buildTokenRecord({
    shopId: shop.shopId,
    tokens: tokens,
    etsyEmail: etsyEmail,
    shopName: shop.shopName,
    shopIds: shop.shopIds,
    nowSeconds: now,
  });
  await store.put(shop.shopId, record);
  const body = "<h1>Your Etsy shop is connected</h1>" +
    "<p>Shop connected. Your agent purchases will be screened by the RelayShield Firewall, checked for authorization, and checked against the counterparty screen.</p>" +
    "<p>Next: open the RelayShield console to see the shop and provision the Firewall tenant for the seller's agent.</p>" +
    "<p><a href=\"https://mcpfw.relayshield.net/\">Open the RelayShield console</a></p>";
  return new Response(htmlPage("Etsy shop connected", body), {
    status: 200,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
