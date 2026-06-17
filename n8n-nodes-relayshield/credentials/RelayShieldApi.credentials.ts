import {
	IAuthenticateGeneric,
	ICredentialTestRequest,
	ICredentialType,
	INodeProperties,
} from 'n8n-workflow';

export class RelayShieldApi implements ICredentialType {
	name = 'relayShieldApi';
	displayName = 'RelayShield API';
	icon = 'file:relayshield.svg' as const;
	documentationUrl = 'https://api.relayshield.net/developers';
	properties: INodeProperties[] = [
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			default: '',
			placeholder: 'rs_live_...',
			description: 'Your RelayShield API key. Get one at api.relayshield.net/developers.',
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {
				'X-RS-API-KEY': '={{$credentials.apiKey}}',
			},
		},
	};

	test: ICredentialTestRequest = {
		request: {
			baseURL: 'https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod',
			url: '/v1/intel/cve',
			method: 'GET',
			qs: { keyword: 'test' },
		},
	};
}
