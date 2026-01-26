// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides configuration options for durable agents and workflows.
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
    public DurableOptions()
    {
        this.Workflows = new DurableWorkflowOptions(this);
    }
}
