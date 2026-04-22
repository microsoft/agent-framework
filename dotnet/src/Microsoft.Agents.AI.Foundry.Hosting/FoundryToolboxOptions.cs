// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for Foundry Toolbox MCP integration.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryToolboxOptions
{
    /// <summary>
    /// Gets the list of toolbox names to connect to at startup.
    /// Each name corresponds to a toolbox registered in the Foundry project.
    /// The platform proxy URL is constructed as:
    /// <c>{FOUNDRY_AGENT_TOOLSET_ENDPOINT}/{toolboxName}/mcp?api-version={ApiVersion}</c>
    /// </summary>
    public IList<string> ToolboxNames { get; } = [];

    /// <summary>
    /// Gets or sets the Toolsets API version to use when constructing proxy URLs.
    /// </summary>
    public string ApiVersion { get; set; } = "2025-05-01-preview";

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
    /// For testing only: overrides <c>FOUNDRY_AGENT_TOOLSET_ENDPOINT</c>.
    /// Not part of the public API.
    /// </summary>
    internal string? EndpointOverride { get; set; }
}
