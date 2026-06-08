// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides Azure Functions–specific configuration for durable workflows.
/// </summary>
internal sealed class FunctionsDurableOptions : DurableOptions
{
    private readonly HashSet<string> _statusEndpointWorkflows = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _mcpToolTriggerWorkflows = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>
    /// Enables the status HTTP endpoint for the specified workflow.
    /// </summary>
    internal void EnableStatusEndpoint(string workflowName)
    {
        this._statusEndpointWorkflows.Add(workflowName);
    }

    /// <summary>
    /// Returns whether the status endpoint is enabled for the specified workflow.
    /// </summary>
    internal bool IsStatusEndpointEnabled(string workflowName)
    {
        return this._statusEndpointWorkflows.Contains(workflowName);
    }

    /// <summary>
    /// Enables the MCP tool trigger for the specified workflow.
    /// </summary>
    internal void EnableMcpToolTrigger(string workflowName)
    {
        this._mcpToolTriggerWorkflows.Add(workflowName);
    }

    /// <summary>
    /// Returns whether the MCP tool trigger is enabled for the specified workflow.
    /// </summary>
    internal bool IsMcpToolTriggerEnabled(string workflowName)
    {
        return this._mcpToolTriggerWorkflows.Contains(workflowName);
    }
}
