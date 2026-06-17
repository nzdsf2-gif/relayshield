"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.RelayShield = void 0;
const n8n_workflow_1 = require("n8n-workflow");
const API_BASE = 'https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod';
class RelayShield {
    constructor() {
        this.description = {
            displayName: 'RelayShield',
            name: 'relayShield',
            icon: 'file:relayshield.svg',
            group: ['transform'],
            version: 1,
            subtitle: '={{$parameter["operation"]}}',
            description: 'Breach detection, SIM swap monitoring, infostealer exposure, domain lookalike scanning, and threat intelligence IOC lookup via RelayShield.',
            defaults: {
                name: 'RelayShield',
            },
            inputs: [n8n_workflow_1.NodeConnectionTypes.Main],
            outputs: [n8n_workflow_1.NodeConnectionTypes.Main],
            usableAsTool: true,
            credentials: [
                {
                    name: 'relayShieldApi',
                    required: true,
                },
            ],
            properties: [
                // ----------------------------------------------------------------
                // Operation selector — alphabetical order required by linter
                // ----------------------------------------------------------------
                {
                    displayName: 'Operation',
                    name: 'operation',
                    type: 'options',
                    noDataExpression: true,
                    options: [
                        {
                            name: 'Breach Check',
                            value: 'breach',
                            description: 'Check if an email address appears in known data breaches',
                            action: 'Check an email address for breach exposure',
                        },
                        {
                            name: 'Domain Lookalike Scan',
                            value: 'domain',
                            description: 'Scan for typosquat and lookalike domains registered to impersonate a domain',
                            action: 'Scan a domain for lookalikes and typosquats',
                        },
                        {
                            name: 'Infostealer Check',
                            value: 'infostealer',
                            description: 'Check if credentials appear in criminal infostealer log markets',
                            action: 'Check an email for infostealer log exposure',
                        },
                        {
                            name: 'OAuth Watchlist Check',
                            value: 'oauthWatchlist',
                            description: 'Check if a breach exposes credentials used with high-risk OAuth apps',
                            action: 'Check an email for o auth supply chain exposure',
                        },
                        {
                            name: 'SIM Swap Detection',
                            value: 'simSwap',
                            description: 'Detect active SIM swap or port-out fraud via carrier-level query',
                            action: 'Detect sim swap or port out fraud on a phone number',
                        },
                        {
                            name: 'Threat Intelligence — CVE Lookup',
                            value: 'intelCve',
                            description: 'Query the CISA Known Exploited Vulnerabilities catalog, cross-referenced for ransomware activity',
                            action: 'Look up a CVE or keyword in the CISA KEV catalog',
                        },
                        {
                            name: 'Threat Intelligence — IOC Lookup',
                            value: 'intelTelegram',
                            description: 'Query RelayShield\'s live IOC database (criminal Telegram channels, ThreatFox, URLhaus) for a domain, IP, email, phone, or wallet address',
                            action: 'Look up an indicator of compromise in the threat intelligence database',
                        },
                    ],
                    default: 'breach',
                },
                // ----------------------------------------------------------------
                // Breach / Infostealer / OAuth Watchlist — email
                // ----------------------------------------------------------------
                {
                    displayName: 'Email',
                    name: 'email',
                    type: 'string',
                    placeholder: 'user@example.com',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['breach', 'infostealer', 'oauthWatchlist'] },
                    },
                    description: 'Email address to check',
                },
                // ----------------------------------------------------------------
                // SIM Swap — phone
                // ----------------------------------------------------------------
                {
                    displayName: 'Phone Number',
                    name: 'phone',
                    type: 'string',
                    placeholder: '+12125551234',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['simSwap'] },
                    },
                    description: 'Phone number in E.164 format (+country code + number)',
                },
                // ----------------------------------------------------------------
                // Domain Lookalike
                // ----------------------------------------------------------------
                {
                    displayName: 'Domain',
                    name: 'domain',
                    type: 'string',
                    placeholder: 'example.com',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['domain'] },
                    },
                    description: 'Domain to scan for lookalikes (e.g. example.com)',
                },
                // ----------------------------------------------------------------
                // IOC Lookup
                // ----------------------------------------------------------------
                {
                    displayName: 'Indicator',
                    name: 'indicator',
                    type: 'string',
                    placeholder: 'evil.com or 1.2.3.4 or user@example.com',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['intelTelegram'] },
                    },
                    description: 'The IOC value to look up — domain, IP, email, phone, or wallet address',
                },
                {
                    displayName: 'Indicator Type',
                    name: 'indicatorType',
                    type: 'options',
                    // alphabetical order required by linter
                    options: [
                        { name: 'Domain', value: 'domain' },
                        { name: 'Email', value: 'email' },
                        { name: 'IP Address', value: 'ip' },
                        { name: 'Phone', value: 'phone' },
                        { name: 'Wallet Address', value: 'wallet' },
                    ],
                    default: 'domain',
                    required: true,
                    displayOptions: {
                        show: { operation: ['intelTelegram'] },
                    },
                    description: 'Type of indicator being queried',
                },
                // ----------------------------------------------------------------
                // CVE Lookup
                // ----------------------------------------------------------------
                {
                    displayName: 'Lookup By',
                    name: 'cveLookupBy',
                    type: 'options',
                    options: [
                        { name: 'CVE ID', value: 'cve_id' },
                        { name: 'Keyword', value: 'keyword' },
                    ],
                    default: 'cve_id',
                    required: true,
                    displayOptions: {
                        show: { operation: ['intelCve'] },
                    },
                },
                {
                    displayName: 'CVE ID',
                    name: 'cveId',
                    type: 'string',
                    placeholder: 'CVE-2024-1234',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['intelCve'], cveLookupBy: ['cve_id'] },
                    },
                    description: 'CVE identifier to look up (e.g. CVE-2024-12345)',
                },
                {
                    displayName: 'Keyword',
                    name: 'cveKeyword',
                    type: 'string',
                    placeholder: 'apache, exchange, citrix...',
                    default: '',
                    required: true,
                    displayOptions: {
                        show: { operation: ['intelCve'], cveLookupBy: ['keyword'] },
                    },
                    description: 'Vendor, product, or vulnerability keyword to search in CISA KEV',
                },
            ],
        };
    }
    async execute() {
        const items = this.getInputData();
        const returnData = [];
        const credentials = await this.getCredentials('relayShieldApi');
        const apiKey = credentials.apiKey;
        for (let i = 0; i < items.length; i++) {
            try {
                const operation = this.getNodeParameter('operation', i);
                let responseData;
                if (operation === 'breach') {
                    const email = this.getNodeParameter('email', i);
                    responseData = await relayShieldPost(this, '/v1/metered/breach', { email }, apiKey);
                }
                else if (operation === 'simSwap') {
                    const phone = this.getNodeParameter('phone', i);
                    responseData = await relayShieldPost(this, '/v1/metered/sim-swap', { phone }, apiKey);
                }
                else if (operation === 'infostealer') {
                    const email = this.getNodeParameter('email', i);
                    responseData = await relayShieldPost(this, '/v1/metered/infostealer', { email }, apiKey);
                }
                else if (operation === 'domain') {
                    const domain = this.getNodeParameter('domain', i);
                    responseData = await relayShieldPost(this, '/v1/metered/domain', { domain }, apiKey);
                }
                else if (operation === 'oauthWatchlist') {
                    const email = this.getNodeParameter('email', i);
                    responseData = await relayShieldPost(this, '/v1/metered/oauth-watchlist', { email }, apiKey);
                }
                else if (operation === 'intelTelegram') {
                    const indicator = this.getNodeParameter('indicator', i);
                    const type = this.getNodeParameter('indicatorType', i);
                    responseData = await relayShieldGet(this, `/v1/intel/telegram?indicator=${encodeURIComponent(indicator)}&type=${type}`, apiKey);
                }
                else if (operation === 'intelCve') {
                    const lookupBy = this.getNodeParameter('cveLookupBy', i);
                    if (lookupBy === 'cve_id') {
                        const cveId = this.getNodeParameter('cveId', i);
                        responseData = await relayShieldGet(this, `/v1/intel/cve?cve_id=${encodeURIComponent(cveId)}`, apiKey);
                    }
                    else {
                        const keyword = this.getNodeParameter('cveKeyword', i);
                        responseData = await relayShieldGet(this, `/v1/intel/cve?keyword=${encodeURIComponent(keyword)}`, apiKey);
                    }
                }
                else {
                    throw new n8n_workflow_1.NodeOperationError(this.getNode(), `Unknown operation: ${operation}`, { itemIndex: i });
                }
                returnData.push({ json: responseData, pairedItem: { item: i } });
            }
            catch (error) {
                if (this.continueOnFail()) {
                    returnData.push({ json: { error: error.message }, pairedItem: { item: i } });
                    continue;
                }
                throw new n8n_workflow_1.NodeApiError(this.getNode(), error, { itemIndex: i });
            }
        }
        return [returnData];
    }
}
exports.RelayShield = RelayShield;
// ---------------------------------------------------------------------------
// HTTP helpers — pass IExecuteFunctions for proper NodeApiError context
// ---------------------------------------------------------------------------
async function relayShieldPost(ctx, path, body, apiKey) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-RS-API-KEY': apiKey,
        },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        const text = await response.text();
        throw new n8n_workflow_1.NodeApiError(ctx.getNode(), { message: `RelayShield API error ${response.status}: ${text}` });
    }
    return response.json();
}
async function relayShieldGet(ctx, pathWithQuery, apiKey) {
    const response = await fetch(`${API_BASE}${pathWithQuery}`, {
        method: 'GET',
        headers: { 'X-RS-API-KEY': apiKey },
    });
    if (!response.ok) {
        const text = await response.text();
        throw new n8n_workflow_1.NodeApiError(ctx.getNode(), { message: `RelayShield API error ${response.status}: ${text}` });
    }
    return response.json();
}
//# sourceMappingURL=RelayShield.node.js.map