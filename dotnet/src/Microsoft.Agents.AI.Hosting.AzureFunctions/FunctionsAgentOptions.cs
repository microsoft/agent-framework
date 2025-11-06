// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides configuration options for enabling and customizing function triggers for an agent.
/// </summary>
public sealed class FunctionsAgentOptions
{
    /// <summary>
    /// Gets or sets the configuration options for the HTTP trigger endpoint.
    /// </summary>
    public HttpTriggerOptions HttpTrigger { get; set; } = new(false);

    /// <summary>
    /// Gets or sets the options used to configure the MCP tool trigger behavior.
    /// </summary>
    public McpToolTriggerOptions McpToolTrigger { get; set; } = new(false);
}
