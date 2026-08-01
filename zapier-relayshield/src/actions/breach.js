const { rsPost } = require('../utils');

module.exports = {
  key: 'breach',
  noun: 'Breach',
  display: {
    label: 'Check Breach Exposure',
    description:
      'Checks whether an email address appears in known data breaches. Returns breach count, breach names, dates, and exposed data classes.',
  },
  operation: {
    inputFields: [
      { key: 'email', label: 'Email Address', required: true, type: 'string',
        helpText: 'Email address to check for breach exposure.' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/breach', { email: bundle.inputData.email });
      return { id: bundle.inputData.email, ...result };
    },
    sample: {
      id: 'user@example.com',
      record_type: 'credential_exposure',
      email: 'user@example.com',
      breach_count: 3,
      breaches: [{ name: 'LinkedIn', breach_date: '2021-06-22', data_classes: ['Emails', 'Passwords'] }],
    },
  },
};
