const { rsPost } = require('../utils');

module.exports = {
  key: 'ransomwareRisk',
  noun: 'Ransomware Risk',
  display: {
    label: 'Check Ransomware Risk',
    description:
      'Checks a domain against ransomware group victim listings covering 100+ groups, plus the pre-ransomware credential corpus. Returns victim listing status, responsible groups, and the count of credentials found in stealer logs before the incident.',
  },
  operation: {
    inputFields: [
      { key: 'domain', label: 'Domain', required: true, type: 'string',
        helpText: 'Domain to check (e.g. acme.com).' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/ransomware-risk', { domain: bundle.inputData.domain });
      return { id: bundle.inputData.domain, ...result };
    },
    sample: {
      id: 'acme.com',
      domain: 'acme.com',
      on_victim_list: false,
      victim_groups: [],
      pre_ransomware_ioc_count: 0,
      risk_level: 'CLEAN',
    },
  },
};
