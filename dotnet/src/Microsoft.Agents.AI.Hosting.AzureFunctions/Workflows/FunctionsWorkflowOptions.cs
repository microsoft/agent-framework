// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.Workflows;

/// <summary>
/// Provides configuration options for enabling and customizing function triggers for a workflow.
/// </summary>
public sealed class FunctionsWorkflowOptions
{
    /// <summary>
    /// Gets or sets the options used to configure the MCP tool trigger behavior.
    /// </summary>
    /// <remarks>
    /// By default, MCP tool trigger is disabled for workflows.
    /// </remarks>
    public McpToolTriggerOptions McpToolTrigger { get; set; } = new(false);
}
