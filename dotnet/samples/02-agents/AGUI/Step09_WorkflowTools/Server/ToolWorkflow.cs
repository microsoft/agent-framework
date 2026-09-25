// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

namespace AGUI.WorkflowTools;

/// <summary>
/// Creates the tool-enabled workflow used by the sample and its integration test.
/// </summary>
public static class ToolWorkflow
{
    /// <summary>
    /// Creates a workflow containing the supplied tool-enabled agent.
    /// </summary>
    /// <param name="agent">The tool-enabled agent.</param>
    /// <returns>The workflow.</returns>
    public static Workflow Create(AIAgent agent)
        => new SequentialWorkflowBuilder(agent).Build();
}
