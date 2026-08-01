const { rsPost } = require('../utils');

module.exports = {
  key: 'infostealer',
  noun: 'Infostealer',
  display: {
    label: 'Check Infostealer Exposure',
    description:
      'Checks whether credentials appear in criminal infostealer malware logs. A single infected device exposes every saved password across 50+ services at once, including banking, email, SaaS tools, and active session cookies that bypass 2FA.',
  },
  operation: {
    inputFields: [
      { key: 'email', label: 'Email Address', required: true, type: 'string',
        helpText: 'Email address to check for infostealer malware log exposure.' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/infostealer', { email: bundle.inputData.email });
      return { id: bundle.inputData.email, ...result };
    },
    sample: {
      id: 'user@example.com',
      record_type: 'credential_exposure',
      email: 'user@example.com',
      found: false,
      stealer_count: 0,
      stealers: [],
    },
  },
};
