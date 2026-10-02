// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

namespace AGUI.WorkflowConcurrent;

/// <summary>
/// Creates the concurrent workflow used by the sample and its integration test.
/// </summary>
public static class ConcurrentWorkflow
{
    /// <summary>
    /// Creates a workflow that runs all supplied agents concurrently.
    /// </summary>
    /// <param name="agents">The agents to run concurrently.</param>
    /// <returns>The concurrent workflow.</returns>
    public static Workflow Create(params AIAgent[] agents)
        => new ConcurrentWorkflowBuilder(agents).Build();
}
