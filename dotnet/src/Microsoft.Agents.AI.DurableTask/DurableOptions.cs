// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.DurableTask.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides configuration options for durable agents and workflows.
/// </summary>
[DebuggerDisplay("Workflows = {Workflows.Workflows.Count}, Agents = {Agents.AgentCount}")]
public sealed class DurableOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableOptions"/> class.
    /// </summary>
    internal DurableOptions()
    {
        this.Workflows = new DurableWorkflowOptions(this);
    }

    /// <summary>
    /// Gets the configuration options for durable agents.
    /// </summary>
    public DurableAgentsOptions Agents { get; } = new();

    /// <summary>
    /// Gets the configuration options for durable workflows.
    /// </summary>
    public DurableWorkflowOptions Workflows { get; }
}
