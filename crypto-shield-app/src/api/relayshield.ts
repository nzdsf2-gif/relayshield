// RelayShield API client for Crypto Shield mobile app
// All calls go through the RS metered endpoints using the user's API key

const RS_BASE = "https://api.relayshield.net";

async function rsPost(endpoint: string, body: object, apiKey?: string | null) {
  // Free-tier scans call the contract-reputation endpoints with no key at all
  // (see FREE_SCAN_TYPES in ScanScreen). apiKey is `string | null` upstream, so
  // without this the header would be sent as the literal string "null" — which
  // works today only because these endpoints ignore it, and would silently break
  // the moment they start validating.
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) headers["X-RS-API-KEY"] = apiKey;

  const resp = await fetch(`${RS_BASE}${endpoint}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`RS API error ${resp.status}`);
  const json = await resp.json();
  // Unwrap { ok: true, data: {...} } envelope if present
  return json?.data ?? json;
}

async function rsGet(endpoint: string, apiKey: string) {
  const resp = await fetch(`${RS_BASE}${endpoint}`, {
    headers: { "X-API-Key": apiKey },
  });
  if (!resp.ok) throw new Error(`RS API error ${resp.status}`);
  return resp.json();
}

// Retrieve the API key auto-provisioned for a Crypto Shield Pro subscriber,
// by the email they used at Stripe checkout — no separate developer signup,
// no separate card. Throws with the server's error message if no active
// subscription is found for that email.
export async function linkCryptoShieldSubscription(email: string): Promise<string> {
  const resp = await fetch(`${RS_BASE}/developer/cs-mobile-link?email=${encodeURIComponent(email)}`);
  const json = await resp.json();
  if (!resp.ok || !json?.ok) {
    throw new Error(json?.error || "No active subscription found for that email.");
  }
  return json.data.api_key;
}

// Identity risk score for a wallet's associated domain or email
export async function getIdentityRisk(domain: string, apiKey: string) {
  return rsPost("/v1/metered/identity-risk-score", { domain }, apiKey);
}

// Check infostealer exposure for an email
export async function checkInfostealer(email: string, apiKey: string) {
  return rsPost("/v1/metered/infostealer", { email }, apiKey);
}

// Check breach exposure for an email
export async function checkBreach(email: string, apiKey: string) {
  return rsPost("/v1/metered/breach", { email }, apiKey);
}

// NHI exposure — check if wallet address or API key appears in stealer logs
export async function checkNHI(domain: string, apiKey: string) {
  return rsPost("/v1/metered/nhi-exposure", { domain }, apiKey);
}

// Supply chain risk for Solana ecosystem vendors
export async function checkSupplyChain(vendorDomains: string[], apiKey: string) {
  return rsPost("/v1/metered/supply-chain", { vendor_domains: vendorDomains }, apiKey);
}

// SIM swap check
export async function checkSimSwap(phone: string, apiKey: string) {
  return rsPost("/v1/metered/sim-swap", { phone }, apiKey);
}

// GoPlus token risk check (already integrated in RS)
export async function checkTokenRisk(tokenAddress: string, chainId: string, apiKey: string) {
  return rsPost("/v1/token-security", { contract_address: tokenAddress, chain_id: chainId }, apiKey);
}

// Bulk identity risk for multiple wallets/emails
export async function bulkIdentityRisk(targets: { domain: string; agents?: string[] }[], apiKey: string) {
  return rsPost("/v1/metered/bulk-identity-risk", { targets }, apiKey);
}

// Trending threat intel
export async function getTrendingThreats(hours: number = 24, apiKey: string) {
  return rsPost("/v1/intel/trending", { hours }, apiKey);
}

// Wallet risk — multi-chain (EVM/Solana/TON/Bitcoin)
export async function scanWalletRisk(address: string, apiKey: string) {
  return rsPost("/v1/wallet-risk", { address }, apiKey);
}

// Account info — returns plan tier and intel_access flag
export async function getAccountInfo(apiKey: string) {
  return rsPost("/v1/account/info", {}, apiKey);
}

// EVM token approval scanner
export async function checkApprovals(address: string, chainId: string, apiKey: string) {
  return rsPost("/v1/approval-security", { address, chain_id: chainId }, apiKey);
}

// Alchemy simulate asset changes (EVM)
export async function simulateTransaction(
  from: string, to: string, data: string, value: string, alchemyKey: string
) {
  const resp = await fetch(`https://eth-mainnet.g.alchemy.com/v2/${alchemyKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0", id: 1,
      method: "alchemy_simulateAssetChanges",
      params: [{ from, to, data, value }],
    }),
  });
  if (!resp.ok) throw new Error(`Alchemy simulate error ${resp.status}`);
  const json = await resp.json();
  return json?.result ?? json;
}

// Register Expo push token for server-side wallet monitoring alerts
export async function registerPushToken(pushToken: string, wallets: ({ address: string; chain: string; label: string } | string)[], apiKey: string, nftCollections: string[] = [], telegramId?: string) {
  return rsPost("/v1/app/register-push", { push_token: pushToken, wallet_addresses: wallets, nft_collections: nftCollections, ...(telegramId ? { telegram_id: telegramId } : {}) }, apiKey);
}

// Fetch the most recent alert as authoritative server state — the push_token
// itself is the identifier, no API key needed. More reliable than depending
// on the OS notification-received event, which doesn't fire consistently
// across Android/FCM/Expo app-state combinations.
export async function getLastAlert(pushToken: string): Promise<{ title: string; body: string; timestamp: string } | null> {
  const resp = await fetch(`${RS_BASE}/v1/app/last-alert?push_token=${encodeURIComponent(pushToken)}`);
  if (!resp.ok) return null;
  const json = await resp.json();
  return json?.data?.last_alert ?? null;
}

// Zero-touch counterpart to linkCryptoShieldSubscription — exchanges a Stripe
// Checkout Session ID (captured from the deep link back into the app after
// payment) for the auto-provisioned API key, no email typing required. The
// session ID itself is real proof of purchase.
export async function linkCryptoShieldSubscriptionBySession(sessionId: string): Promise<string> {
  const resp = await fetch(`${RS_BASE}/developer/cs-mobile-link-by-session?session_id=${encodeURIComponent(sessionId)}`);
  const json = await resp.json();
  if (!resp.ok || !json?.ok) {
    throw new Error(json?.error || "Could not confirm that checkout session yet.");
  }
  return json.data.api_key;
}

// Get a Stripe-hosted billing portal link (cancel, update card, view invoices)
// for a Crypto Shield Pro subscriber -- self-service, no email to support
// needed. Prefers the already-linked apiKey (one tap, no retyping); pass an
// email instead as a fallback for the rare case there's no linked key yet.
// Throws if no active subscription is found.
export async function getCryptoShieldBillingPortalUrl(opts: { apiKey?: string; email?: string }): Promise<string> {
  const params = opts.apiKey
    ? `api_key=${encodeURIComponent(opts.apiKey)}`
    : `email=${encodeURIComponent(opts.email ?? "")}`;
  const resp = await fetch(`${RS_BASE}/developer/cs-mobile-portal?${params}`);
  const json = await resp.json();
  if (!resp.ok || !json?.ok) {
    throw new Error(json?.error || "Could not open billing management right now.");
  }
  return json.data.portal_url;
}

// Check the latest published Crypto Shield version on the Solana dApp Store
// (reads the on-chain Release NFT group) — no API key needed.
export async function getCSMobileLatestVersion(): Promise<string | null> {
  try {
    const resp = await fetch(`${RS_BASE}/v1/app/cs-mobile-latest-version`);
    if (!resp.ok) return null;
    const json = await resp.json();
    return json?.data?.latest_version ?? null;
  } catch {
    return null;
  }
}

// Submit in-app feedback (thumbs up/down + optional comment) — push_token identifies
// the device, no API key needed. One record per device on the backend.
export async function submitFeedback(pushToken: string, rating: "up" | "down", comment?: string): Promise<boolean> {
  try {
    const resp = await fetch(`${RS_BASE}/v1/app/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ push_token: pushToken, rating, comment: comment || "" }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

// dApp reputation scoring via GoPlus
export async function checkDappReputation(url: string, apiKey: string) {
  return rsPost("/v1/dapp-security", { url }, apiKey);
}

// NFT collection floor risk via Magic Eden (Solana)
export async function checkNFTFloor(symbol: string, apiKey: string) {
  return rsPost("/v1/nft-floor", { symbol }, apiKey);
}

// NFT contract security via GoPlus (EVM only) — malicious/fake-collection
// flags, catches the category of scam where a drainer contract is disguised
// as an NFT collection (e.g. fake airdrop/reward NFTs).
export async function checkNFTSecurity(contractAddress: string, chainId: string, apiKey: string) {
  return rsPost("/v1/nft-security", { contract_address: contractAddress, chain_id: chainId }, apiKey);
}

// Rugcheck.xyz Solana token risk (mint authority, freeze authority, honeypot)
export async function checkSolanaTokenRisk(mint: string, apiKey: string) {
  return rsPost("/v1/solana/token-risk", { mint }, apiKey);
}

// SolanaFM address reputation
export async function checkSolanaAddressRisk(address: string, apiKey: string) {
  return rsPost("/v1/solana/address-risk", { address }, apiKey);
}

// Tensor NFT collection floor risk
export async function checkTensorNFT(slug: string, apiKey: string) {
  return rsPost("/v1/solana/nft-tensor", { slug }, apiKey);
}

// Inbound transaction senders for address poisoning detection (all chains via RS server-side keys)
export async function getWalletInbound(address: string, chain: "evm" | "solana" | "ton", apiKey: string) {
  return rsPost("/v1/wallet-inbound", { address, chain }, apiKey);
}

// ── TON Chain ──────────────────────────────────────────────────────────────

// TON address or token — routes through RS Lambda (auto-detects wallet vs token via DexScreener)
export async function checkTONAddress(address: string, apiKey?: string | null) {
  return rsPost("/v1/ton-address", { address }, apiKey);
}

// XRP Ledger address — balance + XRPSCAN advisory fraud flag
export async function checkXRPAddress(address: string, apiKey?: string | null) {
  return rsPost("/v1/xrp-address", { address }, apiKey);
}

// ── BNB Chain (BSC) ────────────────────────────────────────────────────────

// BNB token security — wraps GoPlus with chain_id=56
export async function checkBNBToken(contractAddress: string, apiKey: string) {
  return rsPost("/v1/token-security", { contract_address: contractAddress, chain_id: "56" }, apiKey);
}

// BNB address risk — GoPlus address security on BSC
export async function checkBNBAddress(address: string, apiKey: string) {
  return rsPost("/v1/address-security", { address, chain_id: "56" }, apiKey);
}

// ── Base (Coinbase L2) ─────────────────────────────────────────────────────

// Basescan address reputation — free public API, Etherscan-compatible
export async function checkBaseAddress(address: string): Promise<{
  address: string; balance_eth: string; tx_count: number;
  risk_level: string; risk_factors: string[]; is_contract: boolean;
  contract_verified: boolean;
}> {
  const risk_factors: string[] = [];
  try {
    // Basescan free API — no key needed for basic lookups
    const [balResp, txResp] = await Promise.all([
      fetch(`https://api.basescan.org/api?module=account&action=balance&address=${address}&tag=latest`),
      fetch(`https://api.basescan.org/api?module=account&action=txlist&address=${address}&page=1&offset=1&sort=desc`),
    ]);
    const balData = await balResp.json();
    const txData  = await txResp.json();

    const balanceWei = balData?.result ?? "0";
    const balance_eth = (parseInt(balanceWei) / 1e18).toFixed(6) + " ETH";
    const txs = txData?.result ?? [];
    const tx_count = Array.isArray(txs) ? txs.length : 0;

    // Check if contract (code exists)
    const codeResp = await fetch(`https://api.basescan.org/api?module=contract&action=getabi&address=${address}`);
    const codeData = await codeResp.json();
    const is_contract = codeData?.status === "1";
    const contract_verified = is_contract && !!codeData?.result && codeData.result !== "Contract source code not verified";

    if (is_contract && !contract_verified) risk_factors.push("Unverified contract — source code not public");

    return {
      address, balance_eth, tx_count,
      risk_level: risk_factors.length > 0 ? "MEDIUM" : "LOW",
      risk_factors, is_contract, contract_verified,
    };
  } catch (e) {
    throw new Error(`Basescan lookup failed: ${e}`);
  }
}

// Base token security — GoPlus with chain_id=8453
export async function checkBaseToken(contractAddress: string, apiKey: string) {
  return rsPost("/v1/token-security", { contract_address: contractAddress, chain_id: "8453" }, apiKey);
}

// Register Base network addresses in Alchemy webhook
export async function registerBaseWebhook(
  alchemyAuthToken: string,
  alchemyWebhookId: string,
  addresses: string[]
): Promise<boolean> {
  try {
    // Alchemy webhook for Base uses the same endpoint — network is set at webhook creation time
    const resp = await fetch("https://dashboard.alchemy.com/api/update-webhook-addresses", {
      method: "PATCH",
      headers: { "Content-Type": "application/json", "X-Alchemy-Token": alchemyAuthToken },
      body: JSON.stringify({
        webhook_id: alchemyWebhookId,
        addresses_to_add: addresses,
        addresses_to_remove: [],
      }),
    });
    return resp.ok;
  } catch { return false; }
}
