const API_BASE = 'https://api.relayshield.net';

const rsPost = async (z, bundle, path, body) => {
  const response = await z.request({
    url: `${API_BASE}${path}`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-RS-API-KEY': bundle.authData.apiKey,
    },
    body,
  });
  const data = response.json;
  if (!data.ok) {
    throw new z.errors.Error(data.error || 'RelayShield API error', 'API_ERROR', response.status);
  }
  return data.data;
};

module.exports = { API_BASE, rsPost };
