// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for Foundry Toolbox MCP integration.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FoundryToolboxOptions
{
    /// <summary>
    /// Gets the list of toolbox names to connect to at startup.
    /// Each name corresponds to a toolbox registered in the Foundry project.
    /// The platform proxy URL is constructed as:
    /// <c>{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{toolboxName}/mcp?api-version={ApiVersion}</c>
    /// per <c>tools-integration-spec.md</c> §2–§3.
    /// </summary>
    public IList<string> ToolboxNames { get; } = [];

    /// <summary>
    /// Gets or sets the Toolboxes API version to use when constructing proxy URLs.
    /// </summary>
    public string ApiVersion { get; set; } = "v1";

    /// <summary>
    /// Gets or sets a value indicating whether per-request toolbox markers (referenced via
    /// <c>foundry-toolbox://</c> on the wire) are restricted to toolboxes pre-registered
    /// via <see cref="ToolboxNames"/>. When <see langword="true"/> (the default), a request
    /// that references an unknown toolbox is rejected. When <see langword="false"/>, the
    /// server lazily opens an MCP connection for the referenced toolbox on first use and
    /// caches it.
    /// </summary>
    public bool StrictMode { get; set; } = true;

    /// <summary>
    /// Gets or sets the optional exact HTTPS origins allowed for OAuth consent links.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Every surfaced consent link must be a safe absolute HTTPS URL, whatever this property is set to.
    /// Leave this property <see langword="null"/> to accept any such link without restricting its origin.
    /// When a collection is provided, every consent link must also match one of its normalized origins,
    /// so an empty collection rejects every consent link. Duplicate entries are ignored after normalization.
    /// </para>
    /// <para>
    /// Configure origins such as <c>https://auth.example.com</c>; entries with a path, query, or fragment
    /// are rejected when the toolbox service is constructed. A consent link that fails the policy fails
    /// the response instead of being surfaced.
    /// </para>
    /// </remarks>
    public IList<string>? AllowedOAuthConsentOrigins { get; set; }

    /// <summary>
    /// For testing only: overrides the toolbox proxy base URL (skipping the
    /// <c>FOUNDRY_PROJECT_ENDPOINT</c>-derived default). When set, the proxy URL
    /// becomes <c>{EndpointOverride}/toolboxes/{toolboxName}/mcp?api-version={ApiVersion}</c>.
    /// Not part of the public API.
    /// </summary>
    internal string? EndpointOverride { get; set; }
}
