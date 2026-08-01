const { rsPost } = require('../utils');

module.exports = {
  key: 'identityGraph',
  noun: 'Identity Correlation',
  display: {
    label: 'Check Identity Correlation',
    description:
      'Links an email to associated phone numbers and domains seen alongside it in criminal channel dumps. Pivots from one compromised identifier to others exposed in the same breach or stealer log.',
  },
  operation: {
    inputFields: [
      { key: 'email', label: 'Email Address', required: true, type: 'string' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/identity-graph', { email: bundle.inputData.email });
      return { id: bundle.inputData.email, ...result };
    },
    sample: {
      id: 'user@example.com',
      email: 'user@example.com',
      found: false,
      correlated_identifiers: 0,
      correlated_phones: [],
      correlated_domains: [],
      sources: [],
    },
  },
};
