// Copyright (c) Microsoft. All rights reserved.

using Azure.Core;
using Azure.Identity;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// A <see cref="TokenCredential"/> for local Docker debugging only.
///
/// When debugging and testing a hosted agent in a local Docker container, Azure CLI
/// and other interactive credentials are not available. This credential reads a
/// pre-fetched bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable.
///
/// This should NOT be used in production. Tokens expire (around one hour) and cannot be refreshed.
/// In production, the Foundry platform injects a managed identity automatically.
///
/// Generate a token on your host and pass it to the container:
///   export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
///   docker run -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN ...
/// </summary>
public sealed class DevTemporaryTokenCredential : TokenCredential
{
    private const string EnvironmentVariable = "AZURE_BEARER_TOKEN";
    private readonly string? _token;

    /// <summary>
    /// Initializes a new instance of the <see cref="DevTemporaryTokenCredential"/> class.
    /// Reads the bearer token from the <c>AZURE_BEARER_TOKEN</c> environment variable when present.
    /// </summary>
    public DevTemporaryTokenCredential()
    {
        this._token = Environment.GetEnvironmentVariable(EnvironmentVariable);
    }

    /// <inheritdoc />
    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return this.GetAccessToken();
    }

    /// <inheritdoc />
    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return new ValueTask<AccessToken>(this.GetAccessToken());
    }

    private AccessToken GetAccessToken()
    {
        if (string.IsNullOrEmpty(this._token) || this._token == "DefaultAzureCredential")
        {
            throw new CredentialUnavailableException($"{EnvironmentVariable} environment variable is not set.");
        }

        return new AccessToken(this._token, DateTimeOffset.UtcNow.AddHours(1));
    }
}
