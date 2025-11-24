// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Authentication;

namespace M365Agent;

internal sealed class TokenValidationOptions
{
    /// <summary>
    /// The list of audiences to validate against.
    /// </summary>
    public IList<string>? Audiences { get; set; }

    /// <summary>
    /// TenantId of the Azure Bot. Optional but recommended.
    /// </summary>
    public string? TenantId { get; set; }

    /// <summary>
    /// Additional valid issuers. Optional, in which case the Public Azure Bot Service issuers are used.
    /// </summary>
    public IList<string>? ValidIssuers { get; set; }

    /// <summary>
    /// Can be omitted, in which case public Azure Bot Service and Azure Cloud metadata urls are used.
    /// </summary>
    public bool IsGov { get; set; }

    /// <summary>
    /// Azure Bot Service OpenIdMetadataUrl. Optional, in which case default value depends on IsGov.
    /// </summary>
    /// <see cref="AuthenticationConstants.PublicAzureBotServiceOpenIdMetadataUrl"/>
    /// <see cref="AuthenticationConstants.GovAzureBotServiceOpenIdMetadataUrl"/>
    public string? AzureBotServiceOpenIdMetadataUrl { get; set; }

    /// <summary>
    /// Entra OpenIdMetadataUrl. Optional, in which case default value depends on IsGov.
    /// </summary>
    /// <see cref="AuthenticationConstants.PublicOpenIdMetadataUrl"/>
    /// <see cref="AuthenticationConstants.GovOpenIdMetadataUrl"/>
    public string? OpenIdMetadataUrl { get; set; }

    /// <summary>
    /// Determines if Azure Bot Service tokens are handled. Defaults to true and should always be true until Azure Bot Service sends Entra ID token.
    /// </summary>
    public bool AzureBotServiceTokenHandling { get; set; } = true;

    /// <summary>
    /// OpenIdMetadata refresh interval.  Defaults to 12 hours.
    /// </summary>
    public TimeSpan? OpenIdMetadataRefresh { get; set; }
}
