const { rsPost } = require('../utils');

module.exports = {
  key: 'iocLookup',
  noun: 'IOC Lookup',
  display: {
    label: 'Look Up Threat Indicator',
    description:
      'Queries a live database of 494,000+ distinct indicators, drawn from 5.8 million sightings across 95 monitored channels and 20 authoritative threat feeds, for a domain, IP, email, phone, or wallet address. Returns confidence score, malware family, and threat actor attribution.',
  },
  operation: {
    inputFields: [
      { key: 'indicator', label: 'Indicator', required: true, type: 'string',
        helpText: 'The value to look up — domain, IP address, email, phone, or wallet address.' },
      { key: 'type', label: 'Indicator Type', required: true, type: 'string',
        choices: ['domain', 'ip', 'email', 'phone', 'wallet'],
        helpText: 'Type of indicator.' },
    ],
    perform: async (z, bundle) => {
      const body = { [bundle.inputData.type]: bundle.inputData.indicator, type: bundle.inputData.type };
      const result = await rsPost(z, bundle, '/v1/intel/telegram', body);
      return { id: bundle.inputData.indicator, ...result };
    },
    sample: {
      id: 'example.com',
      record_type: 'ioc_indicator',
      matched: false,
      hit_count: 0,
      hits: [],
    },
  },
};
