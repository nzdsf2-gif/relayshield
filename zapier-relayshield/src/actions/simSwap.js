const { rsPost } = require('../utils');

module.exports = {
  key: 'simSwap',
  noun: 'SIM Swap',
  display: {
    label: 'Check SIM Swap Status',
    description:
      'Detects active SIM swap or port-out fraud on a phone number via a telco carrier lookup database. Returns carrier name, swap timestamp, and line type.',
  },
  operation: {
    inputFields: [
      { key: 'phone', label: 'Phone Number', required: true, type: 'string',
        helpText: 'Phone number in E.164 format (e.g. +12125551234).' },
    ],
    perform: async (z, bundle) => {
      const result = await rsPost(z, bundle, '/v1/metered/sim-swap', { phone: bundle.inputData.phone });
      return { id: bundle.inputData.phone, ...result };
    },
    sample: {
      id: '+12125551234',
      phone: '+12125551234',
      sim_swap_detected: false,
      carrier: 'Verizon',
      line_type: 'mobile',
    },
  },
};
