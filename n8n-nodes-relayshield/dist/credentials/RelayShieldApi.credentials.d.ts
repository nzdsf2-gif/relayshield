import { IAuthenticateGeneric, ICredentialTestRequest, ICredentialType, INodeProperties } from 'n8n-workflow';
export declare class RelayShieldApi implements ICredentialType {
    name: string;
    displayName: string;
    icon: "file:relayshield.svg";
    documentationUrl: string;
    properties: INodeProperties[];
    authenticate: IAuthenticateGeneric;
    test: ICredentialTestRequest;
}
//# sourceMappingURL=RelayShieldApi.credentials.d.ts.map