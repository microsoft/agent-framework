// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Defines additional property keys used by workflow-hosted agents.
/// </summary>
public static class WorkflowAgentAdditionalProperties
{
    /// <summary>
    /// The key for the workflow executor identifier that produced an agent response update.
    /// </summary>
    public const string ExecutorId = "executorId";
}
