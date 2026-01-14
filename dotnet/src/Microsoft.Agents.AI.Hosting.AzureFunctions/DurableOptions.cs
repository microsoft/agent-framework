// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides configuration options for durable features in Azure Functions.
/// </summary>
public sealed class DurableOptions
{
    /// <summary>
    /// Gets the configuration options for durable agents.
    /// </summary>
    public DurableAgentsOptions Agents { get; } = new();

    /// <summary>
    /// Gets the configuration options for durable workflows.
    /// </summary>
    public DurableWorkflowOptions Workflows { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableOptions"/> class.
    /// </summary>
    internal DurableOptions()
    {
        this.Workflows = new DurableWorkflowOptions(this);
    }
}
