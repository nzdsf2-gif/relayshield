import {
	IDataObject,
	IExecuteFunctions,
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
	NodeApiError,
	NodeConnectionTypes,
	NodeOperationError,
} from 'n8n-workflow';

const API_BASE = 'https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod';

export class RelayShield implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'RelayShield',
		name: 'relayShield',
		icon: 'file:relayshield.svg',
		group: ['transform'],
		version: 1,
		subtitle: '={{$parameter["operation"]}}',
		description: 'Breach detection, SIM swap monitoring, infostealer exposure, domain lookalike scanning, supply chain risk, active session hijack detection, and threat intelligence via RelayShield.',
		defaults: {
			name: 'RelayShield',
		},
		inputs: [NodeConnectionTypes.Main],
		outputs: [NodeConnectionTypes.Main],
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
						name: 'Identity Correlation',
						value: 'identityGraph',
						description: 'Link an email to associated phone numbers and domains seen alongside it in criminal channel dumps — pivot from one compromised identifier to find all others',
						action: 'Find identifiers correlated with a compromised email',
					},
					{
						name: 'Infostealer Check',
						value: 'infostealer',
						description: 'Check if credentials appear in criminal infostealer log markets',
						action: 'Check an email for infostealer log exposure',
					},
					{
						name: 'MCP Registry Risk',
						value: 'mcpRegistryRisk',
						description: 'Check an MCP server URL or package name for known-malicious IOC matches, typosquat domains, and newly-registered domain risk',
						action: 'Check an MCP server for registry risk',
					},
					{
						name: 'OAuth & Token Exposure Check',
						value: 'oauthWatchlist',
						description: 'Check HIBP breach history against 31 OAuth apps + live INTEL-5 stealer corpus for stolen tokens across cloud consoles, CI/CD, and SaaS tools',
						action: 'Check an email for oauth and stolen token exposure',
					},
					{
						name: 'Ransomware Risk',
						value: 'ransomwareRisk',
						description: 'Check a domain against 100+ active ransomware group victim lists and pre-ransomware credential corpus',
						action: 'Check a domain for ransomware victim listing or pre ransomware exposure',
					},
					{
						name: 'Secret Scan',
						value: 'secretScan',
						description: 'Scan public GitHub repositories for secrets exposed alongside a monitored domain',
						action: 'Scan for secrets exposed in public repositories',
					},
					{
						name: 'Session Hijack Detection',
						value: 'sessionRisk',
						description: 'Detect stolen active session cookies in RelayShield INTEL-5 corpus — identifies AiTM attacks that bypass 2FA without needing the password',
						action: 'Check an email for active session hijack risk',
					},
					{
						name: 'SIM Swap Detection',
						value: 'simSwap',
						description: 'Detect active SIM swap or port-out fraud via carrier-level query',
						action: 'Detect sim swap or port out fraud on a phone number',
					},
					{
						name: 'Supply Chain Risk',
						value: 'supplyChain',
						description: 'Check vendor domains for breach exposure and infostealer hits — returns per-domain risk score (CRITICAL / HIGH / MEDIUM / LOW)',
						action: 'Check vendor domains for supply chain identity risk',
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
					show: { operation: ['breach', 'infostealer', 'oauthWatchlist', 'sessionRisk', 'identityGraph'] },
				},
				description: 'Email address to check',
			},

			// ----------------------------------------------------------------
			// Ransomware Risk — domain
			// ----------------------------------------------------------------
			{
				displayName: 'Domain',
				name: 'ransomwareDomain',
				type: 'string',
				placeholder: 'acme.com',
				default: '',
				required: true,
				displayOptions: {
					show: { operation: ['ransomwareRisk'] },
				},
				description: 'Domain to check against ransomware victim lists (e.g. acme.com)',
			},

			// ----------------------------------------------------------------
			// Supply Chain — vendor domains / emails
			// ----------------------------------------------------------------
			{
				displayName: 'Vendor Domains',
				name: 'vendorDomains',
				type: 'string',
				placeholder: 'acme.com, widget.io',
				default: '',
				displayOptions: {
					show: { operation: ['supplyChain', 'secretScan'] },
				},
				description: 'Comma-separated vendor domains to check (e.g. acme.com, vendor.io). Max 10 per call for Supply Chain Risk; max 5 for Secret Scan.',
			},
			{
				displayName: 'Vendor Emails (Optional)',
				name: 'vendorEmails',
				type: 'string',
				placeholder: 'alice@acme.com, bob@vendor.io',
				default: '',
				displayOptions: {
					show: { operation: ['supplyChain'] },
				},
				description: 'Comma-separated vendor email addresses — domains are extracted automatically. Can be used instead of or alongside Vendor Domains.',
			},

			// ----------------------------------------------------------------
			// MCP Registry Risk — server URL / package name
			// ----------------------------------------------------------------
			{
				displayName: 'Server URL',
				name: 'mcpServerUrl',
				type: 'string',
				placeholder: 'https://mcp.example.com/sse',
				default: '',
				displayOptions: {
					show: { operation: ['mcpRegistryRisk'] },
				},
				description: 'MCP server URL to check for typosquat domains, known-malicious IOC matches, and newly-registered domain risk. Provide this or Package Name (or both).',
			},
			{
				displayName: 'Package Name (Optional)',
				name: 'mcpPackageName',
				type: 'string',
				placeholder: '@some-scope/mcp-server-package',
				default: '',
				displayOptions: {
					show: { operation: ['mcpRegistryRisk'] },
				},
				description: 'MCP package name, used if Server URL is not available. Checks are more limited without a domain to check.',
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

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];
		const credentials = await this.getCredentials('relayShieldApi');
		const apiKey = credentials.apiKey as string;

		for (let i = 0; i < items.length; i++) {
			try {
				const operation = this.getNodeParameter('operation', i) as string;
				let responseData: unknown;

				if (operation === 'breach') {
					const email = this.getNodeParameter('email', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/breach', { email }, apiKey);

				} else if (operation === 'simSwap') {
					const phone = this.getNodeParameter('phone', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/sim-swap', { phone }, apiKey);

				} else if (operation === 'infostealer') {
					const email = this.getNodeParameter('email', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/infostealer', { email }, apiKey);

				} else if (operation === 'domain') {
					const domain = this.getNodeParameter('domain', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/domain', { domain }, apiKey);

				} else if (operation === 'oauthWatchlist') {
					const email = this.getNodeParameter('email', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/oauth-watchlist', { email }, apiKey);

				} else if (operation === 'sessionRisk') {
					const email = this.getNodeParameter('email', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/session-risk', { email }, apiKey);

				} else if (operation === 'identityGraph') {
					const email = this.getNodeParameter('email', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/identity-graph', { email }, apiKey);

				} else if (operation === 'ransomwareRisk') {
					const domain = this.getNodeParameter('ransomwareDomain', i) as string;
					responseData = await relayShieldPost(this, '/v1/metered/ransomware-risk', { domain }, apiKey);

				} else if (operation === 'supplyChain') {
					const rawDomains = (this.getNodeParameter('vendorDomains', i) as string).trim();
					const rawEmails  = (this.getNodeParameter('vendorEmails',  i) as string).trim();
					const body: Record<string, string[]> = {};
					if (rawDomains) body.vendor_domains = rawDomains.split(',').map((d) => d.trim()).filter(Boolean);
					if (rawEmails)  body.vendor_emails  = rawEmails.split(',').map((e) => e.trim()).filter(Boolean);
					if (!body.vendor_domains && !body.vendor_emails) {
						throw new NodeOperationError(this.getNode(), 'Supply Chain Risk requires at least one Vendor Domain or Vendor Email', { itemIndex: i });
					}
					responseData = await relayShieldPostJson(this, '/v1/metered/supply-chain', body, apiKey);

				} else if (operation === 'secretScan') {
					const rawDomains = (this.getNodeParameter('vendorDomains', i) as string).trim();
					if (!rawDomains) {
						throw new NodeOperationError(this.getNode(), 'Secret Scan requires at least one Vendor Domain', { itemIndex: i });
					}
					const vendor_domains = rawDomains.split(',').map((d) => d.trim()).filter(Boolean);
					responseData = await relayShieldPostJson(this, '/v1/metered/secret-scan', { vendor_domains }, apiKey);

				} else if (operation === 'mcpRegistryRisk') {
					const serverUrl = (this.getNodeParameter('mcpServerUrl', i) as string).trim();
					const packageName = (this.getNodeParameter('mcpPackageName', i) as string).trim();
					if (!serverUrl && !packageName) {
						throw new NodeOperationError(this.getNode(), 'MCP Registry Risk requires a Server URL or Package Name', { itemIndex: i });
					}
					const body: Record<string, string> = {};
					if (serverUrl) body.server_url = serverUrl;
					if (packageName) body.package_name = packageName;
					responseData = await relayShieldPostJson(this, '/v1/metered/mcp-registry-risk', body, apiKey);

				} else if (operation === 'intelTelegram') {
					const indicator = this.getNodeParameter('indicator', i) as string;
					const type = this.getNodeParameter('indicatorType', i) as string;
					responseData = await relayShieldPost(
						this,
						'/v1/intel/telegram',
						{ [type]: indicator, type },
						apiKey,
					);

				} else if (operation === 'intelCve') {
					const lookupBy = this.getNodeParameter('cveLookupBy', i) as string;
					if (lookupBy === 'cve_id') {
						const cveId = this.getNodeParameter('cveId', i) as string;
						responseData = await relayShieldPost(this, '/v1/intel/cve', { cve_id: cveId }, apiKey);
					} else {
						const keyword = this.getNodeParameter('cveKeyword', i) as string;
						responseData = await relayShieldPost(this, '/v1/intel/cve', { keyword }, apiKey);
					}

				} else {
					throw new NodeOperationError(this.getNode(), `Unknown operation: ${operation}`, { itemIndex: i });
				}

				returnData.push({ json: responseData as IDataObject, pairedItem: { item: i } });

			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({ json: { error: (error as Error).message }, pairedItem: { item: i } });
					continue;
				}
				throw new NodeApiError(this.getNode(), error as never, { itemIndex: i });
			}
		}

		return [returnData];
	}
}

// ---------------------------------------------------------------------------
// HTTP helpers — pass IExecuteFunctions for proper NodeApiError context
// ---------------------------------------------------------------------------

async function relayShieldPost(
	ctx: IExecuteFunctions,
	path: string,
	body: Record<string, string>,
	apiKey: string,
): Promise<unknown> {
	return relayShieldPostJson(ctx, path, body, apiKey);
}

// Generic POST helper — accepts any JSON-serialisable body (strings, arrays, etc.)
async function relayShieldPostJson(
	ctx: IExecuteFunctions,
	path: string,
	body: Record<string, unknown>,
	apiKey: string,
): Promise<unknown> {
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
		throw new NodeApiError(ctx.getNode(), { message: `RelayShield API error ${response.status}: ${text}` } as never);
	}
	return response.json();
}

