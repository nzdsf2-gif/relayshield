const { rsPost } = require('../utils');

module.exports = {
  key: 'oauthWatchlist',
  noun: 'OAuth & Token Exposure',
  display: {
    label: 'Check OAuth Token Exposure',
    description:
      'Checks breach history against a 31-app OAuth watchlist plus the live stealer log corpus. Detects stolen OAuth tokens across cloud consoles, CI/CD, identity providers, and SaaS tools with category-level severity scores.',
  },
  operation: {
    inputFields: [
      { key: 'email', label: 'Email Address', required: true, type: 'string' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/oauth-watchlist', { email: bundle.inputData.email });
      return { id: bundle.inputData.email, ...result };
    },
    sample: {
      id: 'user@example.com',
      email: 'user@example.com',
      matched_count: 0,
      matched_apps: [],
      stolen_token_count: 0,
      stolen_tokens: [],
      highest_severity: 'NONE',
    },
  },
};
