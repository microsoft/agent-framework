// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Options for Foundry Toolbox MCP integration.
/// </summary>
public sealed class FoundryToolboxOptions
{
    /// <summary>
    /// Gets the list of toolset names to connect to at startup.
    /// Each name corresponds to a toolset registered in the Foundry project.
    /// The platform proxy URL is constructed as:
    /// <c>{FOUNDRY_AGENT_TOOLSET_ENDPOINT}/{toolsetName}/mcp?api-version={ApiVersion}</c>
    /// </summary>
    public IList<string> ToolsetNames { get; } = new List<string>();

    /// <summary>
    /// Gets or sets the Toolsets API version to use when constructing proxy URLs.
    /// </summary>
    public string ApiVersion { get; set; } = "2025-05-01-preview";

    /// <summary>
    /// For testing only: overrides <c>FOUNDRY_AGENT_TOOLSET_ENDPOINT</c>.
    /// Not part of the public API.
    /// </summary>
    internal string? EndpointOverride { get; set; }
}
