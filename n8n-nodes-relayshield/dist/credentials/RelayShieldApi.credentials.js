"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.RelayShieldApi = void 0;
class RelayShieldApi {
    constructor() {
        this.name = 'relayShieldApi';
        this.displayName = 'RelayShield API';
        this.icon = 'file:relayshield.svg';
        this.documentationUrl = 'https://api.relayshield.net/developers';
        this.properties = [
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
        this.authenticate = {
            type: 'generic',
            properties: {
                headers: {
                    'X-RS-API-KEY': '={{$credentials.apiKey}}',
                },
            },
        };
        this.test = {
            request: {
                baseURL: 'https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod',
                url: '/v1/intel/cve',
                method: 'GET',
                qs: { keyword: 'test' },
            },
        };
    }
}
exports.RelayShieldApi = RelayShieldApi;
//# sourceMappingURL=RelayShieldApi.credentials.js.map