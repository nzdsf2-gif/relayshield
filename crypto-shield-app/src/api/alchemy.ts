// Alchemy API client — gas tracking + webhook management

const COINGECKO_BASE = "https://api.coingecko.com/api/v3";

export interface GasPrice {
  slow: number;     // gwei
  standard: number;
  fast: number;
  baseFee: number;
  level: "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH";
}

export interface StablecoinPrice {
  id: string;
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  pegStatus: "PEGGED" | "WARNING" | "DEPEGGED" | "CRITICAL";
}

const STABLECOINS = [
  // ── Fiat-backed stablecoins ───────────────────────────────────────────────
  { id: "usd-coin",         symbol: "USDC",  name: "USD Coin",          warn: 0.997, crit: 0.990, repeg: 0.999 },
  { id: "tether",           symbol: "USDT",  name: "Tether",            warn: 0.997, crit: 0.990, repeg: 0.999 },
  { id: "dai",              symbol: "DAI",   name: "DAI",               warn: 0.997, crit: 0.990, repeg: 0.999 },
  { id: "frax",             symbol: "FRAX",  name: "Frax",              warn: 0.985, crit: 0.970, repeg: 0.988 },
  { id: "paypal-usd",       symbol: "PYUSD", name: "PayPal USD",        warn: 0.997, crit: 0.990, repeg: 0.999 },
  { id: "first-digital-usd",symbol: "FDUSD", name: "First Digital USD", warn: 0.997, crit: 0.990, repeg: 0.999 },

  // ── Synthetic / yield-bearing dollar RWAs ────────────────────────────────
  // Wider thresholds — NAV accrues yield so price trades slightly above $1
  { id: "ethena-usde",          symbol: "USDe",  name: "Ethena USDe (synthetic)", warn: 0.985, crit: 0.970, repeg: 0.990 },
  { id: "mountain-protocol-usdm",symbol: "USDM", name: "Mountain USDM (RWA)",     warn: 0.993, crit: 0.985, repeg: 0.996 },
  { id: "ondo-us-dollar-yield",  symbol: "USDY",  name: "Ondo USDY (T-Bill RWA)", warn: 0.993, crit: 0.985, repeg: 0.996 },
];

function pegStatus(price: number, coin: typeof STABLECOINS[0]): StablecoinPrice["pegStatus"] {
  if (price < coin.crit) return "CRITICAL";
  if (price < coin.warn) return "WARNING";
  return "PEGGED";
}

const EVM_PROXY = "https://api.relayshield.net/v1/app/evm-rpc";

// Fetch live gas prices via backend EVM proxy — supports ETH mainnet and Base
export async function fetchGasPrice(apiKey: string, network: "eth" | "base" = "eth"): Promise<GasPrice> {
  const headers = { "Content-Type": "application/json", "X-RS-API-KEY": apiKey };

  const [gasPriceResp, blockResp] = await Promise.all([
    fetch(EVM_PROXY, { method: "POST", headers, body: JSON.stringify({ network, jsonrpc: "2.0", method: "eth_gasPrice", params: [], id: 1 }) }),
    fetch(EVM_PROXY, { method: "POST", headers, body: JSON.stringify({ network, jsonrpc: "2.0", method: "eth_getBlockByNumber", params: ["latest", false], id: 2 }) }),
  ]);

  const gasData  = await gasPriceResp.json();
  const blockData = await blockResp.json();

  const gasPriceWei  = parseInt(gasData.result, 16);
  const gasPriceGwei = gasPriceWei / 1e9;
  const baseFeeWei   = parseInt(blockData.result?.baseFeePerGas || "0x0", 16);
  const baseFeeGwei  = baseFeeWei / 1e9;

  // Estimate slow/standard/fast from base fee
  const slow     = Math.round(baseFeeGwei * 1.05);
  const standard = Math.round(baseFeeGwei * 1.15);
  const fast     = Math.round(baseFeeGwei * 1.4);

  let level: GasPrice["level"] = "LOW";
  if (standard > 80)      level = "VERY_HIGH";
  else if (standard > 40) level = "HIGH";
  else if (standard > 15) level = "MEDIUM";

  return { slow, standard, fast, baseFee: Math.round(baseFeeGwei), level };
}

// Fetch stablecoin prices from CoinGecko — accepts optional extra coins beyond the defaults
export async function fetchStablecoinPrices(
  extraCoins: { id: string; symbol: string; name: string; warn?: number; crit?: number; repeg?: number }[] = []
): Promise<StablecoinPrice[]> {
  const allCoins = [
    ...STABLECOINS,
    ...extraCoins.map(c => ({ id: c.id, symbol: c.symbol, name: c.name, warn: c.warn ?? 0.997, crit: c.crit ?? 0.990, repeg: c.repeg ?? 0.999 })),
  ];
  const ids = allCoins.map(s => s.id).join(",");
  const url = `${COINGECKO_BASE}/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`;
  const resp = await fetch(url);
  const data = await resp.json();

  return allCoins.map(coin => {
    const entry   = data[coin.id] || {};
    const price   = entry.usd ?? 1.0;
    const change  = entry.usd_24h_change ?? 0;
    return {
      id:        coin.id,
      symbol:    coin.symbol,
      name:      coin.name,
      price,
      change24h: change,
      pegStatus: pegStatus(price, coin),
    };
  });
}

// Register Alchemy webhook for wallet address activity
export async function registerAddressWebhook(
  alchemyAuthToken: string,
  alchemyWebhookId: string,
  addresses: string[]
): Promise<boolean> {
  try {
    const resp = await fetch(`https://dashboard.alchemy.com/api/update-webhook-addresses`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-Alchemy-Token": alchemyAuthToken,
      },
      body: JSON.stringify({
        webhook_id: alchemyWebhookId,
        addresses_to_add: addresses,
        addresses_to_remove: [],
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

export { STABLECOINS };
