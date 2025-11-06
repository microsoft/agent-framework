// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// This class provides configuration options for the MCP tool trigger for an agent.
/// </summary>
/// <param name="isEnabled">
/// A value indicating whether the MCP tool trigger is enabled for the agent.
/// Set to <see langword="true"/> to enable the trigger; otherwise, <see langword="false"/>.
/// </param>
public sealed class McpToolTriggerOptions(bool isEnabled)
{
    /// <summary>
    /// Gets or sets a value indicating whether MCP tool trigger is enabled for the agent.
    /// </summary>
    public bool IsEnabled { get; set; } = isEnabled;
}
