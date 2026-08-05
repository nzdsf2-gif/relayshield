const { version } = require('./package.json');
const { version: platformVersion } = require('zapier-platform-core');

const authentication = require('./src/authentication');

// Actions
const breach        = require('./src/actions/breach');
const simSwap       = require('./src/actions/simSwap');
const infostealer   = require('./src/actions/infostealer');
const domain        = require('./src/actions/domain');
const supplyChain   = require('./src/actions/supplyChain');
const oauthWatchlist = require('./src/actions/oauthWatchlist');
const sessionRisk   = require('./src/actions/sessionRisk');
const ransomwareRisk = require('./src/actions/ransomwareRisk');
const targetRisk    = require('./src/actions/targetRisk');
const identityGraph = require('./src/actions/identityGraph');
const nhiExposure   = require('./src/actions/nhiExposure');
const iocLookup     = require('./src/actions/iocLookup');

// Triggers
const breachAlert   = require('./src/triggers/breachAlert');

module.exports = {
  version,
  platformVersion,

  authentication,

  triggers: {
    [breachAlert.key]: breachAlert,
  },

  creates: {
    [breach.key]:         breach,
    [simSwap.key]:        simSwap,
    [infostealer.key]:    infostealer,
    [domain.key]:         domain,
    [supplyChain.key]:    supplyChain,
    [oauthWatchlist.key]: oauthWatchlist,
    [sessionRisk.key]:    sessionRisk,
    [ransomwareRisk.key]: ransomwareRisk,
    [targetRisk.key]:     targetRisk,
    [identityGraph.key]:  identityGraph,
    [nhiExposure.key]:    nhiExposure,
    [iocLookup.key]:      iocLookup,
  },

  searches: {},

  flags: {
    cleanInputData: false,  // D028: prevent platform from silently dropping input fields
  },
};
