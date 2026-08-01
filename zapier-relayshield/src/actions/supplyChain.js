const { rsPost } = require('../utils');

module.exports = {
  key: 'supplyChain',
  noun: 'Supply Chain Risk',
  display: {
    label: 'Check Supply Chain Risk',
    description:
      'Checks vendor domains for breach exposure and infostealer hits. Returns a per-domain risk score and a 0-100 dark web composite score. Accepts up to 10 vendor domains per call.',
  },
  operation: {
    inputFields: [
      { key: 'vendor_domains', label: 'Vendor Domains', required: false, type: 'string',
        helpText: 'Comma-separated vendor domains to check (e.g. acme.com, vendor.io). Max 10.' },
      { key: 'vendor_emails', label: 'Vendor Emails (optional)', required: false, type: 'string',
        helpText: 'Comma-separated vendor email addresses — domains extracted automatically.' },
    ],
    perform: async (z, bundle) => {
      const body = {};
      if (bundle.inputData.vendor_domains) {
        body.vendor_domains = bundle.inputData.vendor_domains.split(',').map(d => d.trim()).filter(Boolean);
      }
      if (bundle.inputData.vendor_emails) {
        body.vendor_emails = bundle.inputData.vendor_emails.split(',').map(e => e.trim()).filter(Boolean);
      }
      const result = await rsPost(z, bundle, '/v1/metered/supply-chain', body);
      return { id: Date.now().toString(), ...result };
    },
    sample: {
      id: '1',
      domains_checked: 1,
      highest_risk: 'LOW',
      critical_vendors: [],
      high_risk_vendors: [],
      results: [{ domain: 'acme.com', risk_level: 'LOW', dark_web_score: 0 }],
    },
  },
};
