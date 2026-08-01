/**
 * RelayShield API Key authentication.
 * Users paste their RS API key (rs_live_...) from api.relayshield.net/developers.
 * Validated by calling the breach endpoint with a known safe test value.
 */

const API_BASE = 'https://api.relayshield.net';

const authentication = {
  type: 'custom',

  fields: [
    {
      key: 'apiKey',
      label: 'RelayShield API Key',
      required: true,
      // type: 'password', not 'string' -- Zapier masks password-type auth
      // fields in the UI and redacts them from logs. A credential declared as
      // a plain string is the finding raised in the 2026-07-31 review
      // ("Integration requests authentication credentials appropriately").
      type: 'password',
      helpText:
        'Your RelayShield API key (starts with `rs_live_`). Get yours at [api.relayshield.net/developers](https://api.relayshield.net/developers).',
    },
  ],

  test: {
    url: `${API_BASE}/v1/account/info`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-RS-API-KEY': '{{bundle.authData.apiKey}}',
    },
    body: {},
    removeMissingValuesFrom: {},
  },

  // References the parsed JSON body of the test call above (Zapier's
  // {{json.*}} template scope), not the raw API key — the previous version
  // sliced the literal template-string source before Zapier ever
  // interpolated it, which both produced a broken label and would have
  // exposed part of the raw key even if it had worked.
  connectionLabel: '{{json.data.email}}',
};

module.exports = authentication;
