// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

namespace AGUI.WorkflowSequential;

/// <summary>
/// Creates the sequential workflow used by the sample and its integration test.
/// </summary>
public static class SequentialWorkflow
{
    /// <summary>
    /// Creates a workflow that asks one agent to draft content and another to review it.
    /// </summary>
    /// <param name="writer">The writer agent.</param>
    /// <param name="reviewer">The reviewer agent.</param>
    /// <returns>The sequential workflow.</returns>
    public static Workflow Create(AIAgent writer, AIAgent reviewer)
        => new SequentialWorkflowBuilder(writer, reviewer).Build();
}
