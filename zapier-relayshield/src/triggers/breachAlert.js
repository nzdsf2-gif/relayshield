/**
 * Trigger: New Breach / Infostealer Alert
 *
 * Uses RelayShield's webhook push delivery. When a positive finding fires
 * (breach found, infostealer detected, session hijack, etc.), RelayShield
 * POSTs the result to the registered webhook URL — which Zapier intercepts
 * and fires the Zap.
 *
 * Zapier REST Hook flow:
 *   1. User creates Zap → Zapier calls subscribeHook → we store webhook_url on their API key
 *   2. RS fires alert → POST to webhook_url → Zapier receives → Zap fires
 *   3. User pauses/deletes Zap → Zapier calls unsubscribeHook → we clear webhook_url
 */

const { API_BASE } = require('../utils');

const subscribeHook = async (z, bundle) => {
  const data = { webhook_url: bundle.targetUrl };
  const response = await z.request({
    url: `${API_BASE}/v1/webhook/configure`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-RS-API-KEY': bundle.authData.apiKey,
    },
    body: data,
  });
  return response.json;
};

const unsubscribeHook = async (z, bundle) => {
  const response = await z.request({
    url: `${API_BASE}/v1/webhook/configure`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-RS-API-KEY': bundle.authData.apiKey,
    },
    body: { webhook_url: '' },
  });
  return response.json;
};

// Matches the real webhook payload shape exactly (relayshield_api.py:2649-2661,
// the actual delivery function used for Zapier hook subscriptions — NOT the
// unrelated Expo push helper used elsewhere in the backend). _fire_webhook wraps
// the alert data as { source: "relayshield", payload: {...} }; payload itself is
// { id, endpoint, ...result_data } where result_data is handle_breach()'s
// response body (relayshield_api.py:818-823).
const getFallbackResults = async (z, bundle) => {
  // id value (not the key structure) is time-based so each call to this fallback
  // returns genuinely new content — Zapier's test-record picker treats identical
  // fallback content as already-seen and won't surface it via "Find new records"
  // otherwise. Only the value changes here, never the keys, so this can't
  // reintroduce a key-structure mismatch against the real webhook shape.
  const testId = `test-${Date.now()}@example.com`;
  return [
    {
      source: 'relayshield',
      payload: {
        id: testId,
        endpoint: '/v1/metered/breach',
        email: testId,
        record_type: 'credential_exposure',
        breach_count: 1,
        breaches: [
          { name: 'ExampleBreach', domain: 'example.com', breach_date: '2024-01-01', data_classes: ['Emails', 'Passwords'], is_verified: true },
        ],
      },
      querystring: {},
    },
  ];
};

module.exports = {
  key: 'breachAlert',
  noun: 'Security Alert',
  display: {
    label: 'New Security Alert',
    description:
      'Triggers when a new security finding is detected, such as a breach, infostealer hit, session hijack, or ransomware victim listing. Requires webhook delivery to be configured on your API key.',
  },
  operation: {
    type: 'hook',
    performSubscribe: subscribeHook,
    performUnsubscribe: unsubscribeHook,
    perform: (z, bundle) => [bundle.cleanedRequest],
    performList: getFallbackResults,
    sample: {
      source: 'relayshield',
      payload: {
        id: 'user@example.com',
        endpoint: '/v1/metered/breach',
        email: 'user@example.com',
        record_type: 'credential_exposure',
        breach_count: 1,
        breaches: [
          { name: 'ExampleBreach', domain: 'example.com', breach_date: '2024-01-01', data_classes: ['Emails', 'Passwords'], is_verified: true },
        ],
      },
      querystring: {},
    },
  },
};
