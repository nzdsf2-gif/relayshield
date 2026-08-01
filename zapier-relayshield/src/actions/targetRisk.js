const { rsPost } = require('../utils');

module.exports = {
  key: 'targetRisk',
  noun: 'Target Risk Score',
  display: {
    label: 'Check Target Risk Score',
    description:
      'Estimates the probability that a domain is currently being targeted by threat actors. Combines six independent signals including ransomware victim listing, stealer log hits, breach exposure, criminal channel mentions, and high-EPSS CVEs.',
  },
  operation: {
    inputFields: [
      { key: 'domain', label: 'Domain', required: true, type: 'string',
        helpText: 'Domain to score (e.g. acme.com).' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/target-risk', { domain: bundle.inputData.domain });
      return { id: bundle.inputData.domain, ...result };
    },
    sample: {
      id: 'acme.com',
      record_type: 'threat_prediction',
      domain: 'acme.com',
      target_risk_score: 0,
      probability_tier: 'LOW',
      signals: [],
      recommendation: 'No significant targeting signals detected.',
    },
  },
};
