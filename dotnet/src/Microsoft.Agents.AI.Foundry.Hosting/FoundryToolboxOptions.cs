// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for Foundry Toolbox MCP integration.
/// </summary>
/// <remarks>
/// This type contains optional toolbox behavior only. The required credential and toolbox names are
/// supplied directly to <c>AddFoundryToolboxes</c>.
/// </remarks>
public sealed class FoundryToolboxOptions
{
    internal const string ApiVersion = "v1";
    internal const string DefaultTokenScope = "https://ai.azure.com/.default";

    /// <summary>
    /// Gets the list of toolbox names to connect to at startup.
    /// Each name corresponds to a toolbox registered in the Foundry project.
    /// The platform proxy URL is constructed as:
    /// <c>{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{toolboxName}/mcp?api-version=v1</c>
    /// per <c>tools-integration-spec.md</c> §2–§3.
    /// </summary>
    internal IList<string> ToolboxNames { get; } = [];

    /// <summary>
    /// Gets or sets the Azure token scope used to authenticate requests to the Foundry Toolboxes MCP proxy.
    /// </summary>
    /// <remarks>
    /// The default is <c>https://ai.azure.com/.default</c> for the Azure public cloud.
    /// Set this property to the matching scope for a national cloud and configure the supplied
    /// credential for that cloud's Microsoft Entra authority.
    /// </remarks>
    public string TokenScope { get; set; } = DefaultTokenScope;

    /// <summary>
    /// Gets or sets the exact HTTPS origins allowed for OAuth consent links.
    /// <see langword="null"/> does not restrict the origin; an empty set rejects every origin.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Every surfaced consent link must pass absolute HTTPS URL validation, whatever this property is
    /// set to. Leave this property <see langword="null"/> to skip only the origin restriction. When a
    /// collection is provided, every consent link must also match one of its normalized origins, so an
    /// empty collection rejects every consent link. Duplicate entries are ignored after normalization.
    /// </para>
    /// <para>
    /// Configure absolute <see cref="Uri"/> instances such as <c>https://auth.example.com</c>; entries
    /// with a path, query, or fragment are rejected when the toolbox service is constructed. A consent
    /// link that fails the policy fails the response instead of being surfaced.
    /// </para>
    /// </remarks>
    public ISet<Uri>? AllowedOAuthConsentOrigins { get; set; }

    /// <summary>
    /// For testing only: overrides the toolbox proxy base URL (skipping the
    /// <c>FOUNDRY_PROJECT_ENDPOINT</c>-derived default). When set, the proxy URL
    /// becomes <c>{EndpointOverride}/toolboxes/{toolboxName}/mcp?api-version=v1</c>.
    /// Not part of the public API.
    /// </summary>
    internal string? EndpointOverride { get; set; }
}
