const { rsPost } = require('../utils');

module.exports = {
  key: 'nhiExposure',
  noun: 'NHI Exposure',
  display: {
    label: 'Check NHI Exposure',
    description:
      'Detects non-human identity credentials such as API keys, tokens, and private keys linked to a domain in the stealer log corpus. Covers AWS IAM keys, GitHub PATs, Stripe secrets, and Slack tokens. Accepts an own domain or vendor supply chain domains.',
  },
  operation: {
    inputFields: [
      { key: 'domain', label: 'Domain', required: false, type: 'string',
        helpText: 'Your own domain to check.' },
      { key: 'vendor_domains', label: 'Vendor Domains (optional)', required: false, type: 'string',
        helpText: 'Comma-separated vendor domains for supply chain NHI check.' },
    ],
    perform: async (z, bundle) => {
      const body = {};
      if (bundle.inputData.domain) body.domain = bundle.inputData.domain;
      if (bundle.inputData.vendor_domains) {
        body.vendor_domains = bundle.inputData.vendor_domains.split(',').map(d => d.trim()).filter(Boolean);
      }
      const result = await rsPost(z, bundle, '/v1/metered/nhi-exposure', body);
      return { id: Date.now().toString(), ...result };
    },
    sample: {
      id: '1',
      domains_checked: 1,
      found: false,
      findings: [],
      highest_severity: null,
    },
  },
};
