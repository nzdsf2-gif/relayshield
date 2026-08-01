const { rsPost } = require('../utils');

module.exports = {
  key: 'sessionRisk',
  noun: 'Session Risk',
  display: {
    label: 'Check Session Hijack Risk',
    description:
      'Detects stolen active session cookies linked to an email from criminal stealer log archives. Identifies AiTM attacks that bypass 2FA, where an attacker can reach the account without the password.',
  },
  operation: {
    inputFields: [
      { key: 'email', label: 'Email Address', required: true, type: 'string' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/session-risk', { email: bundle.inputData.email });
      return { id: bundle.inputData.email, ...result };
    },
    sample: {
      id: 'user@example.com',
      record_type: 'credential_exposure',
      email: 'user@example.com',
      found: false,
      session_count: 0,
      highest_severity: null,
      sessions: [],
    },
  },
};
