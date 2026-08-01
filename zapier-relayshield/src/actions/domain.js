const { rsPost } = require('../utils');

module.exports = {
  key: 'domain',
  noun: 'Domain Scan',
  display: {
    label: 'Scan Lookalike Domains',
    description:
      'Scans for typosquat and lookalike domains registered to impersonate a domain. Checks DNS resolution, certificate transparency logs, and Google Safe Browsing.',
  },
  operation: {
    inputFields: [
      { key: 'domain', label: 'Domain', required: true, type: 'string',
        helpText: 'Domain to scan for lookalikes (e.g. example.com).' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/domain', { domain: bundle.inputData.domain });
      return { id: bundle.inputData.domain, ...result };
    },
    sample: {
      id: 'example.com',
      domain: 'example.com',
      lookalike_count: 0,
      lookalikes: [],
    },
  },
};
