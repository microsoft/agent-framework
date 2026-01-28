// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the complete execution plan for a workflow, including parallel execution levels.
/// </summary>
[DebuggerDisplay("Start = {StartExecutorId}, Levels = {Levels.Count}")]
internal sealed class WorkflowExecutionPlan
{
    /// <summary>
    /// The execution levels in order. Each level contains executors that can run in parallel.
    /// </summary>
    public List<WorkflowExecutionLevel> Levels { get; } = [];

    /// <summary>
    /// Maps each executor ID to its predecessors (for Fan-In result aggregation).
    /// </summary>
    public Dictionary<string, List<string>> Predecessors { get; } = [];

    /// <summary>
    /// Maps each executor ID to its successors (for Fan-Out result distribution).
    /// </summary>
    public Dictionary<string, List<string>> Successors { get; } = [];

    /// <summary>
    /// Maps edge connections (sourceId, targetId) to their condition functions.
    /// The condition function takes the predecessor's result and returns true if the edge should be followed.
    /// </summary>
    public Dictionary<(string SourceId, string TargetId), Func<object?, bool>?> EdgeConditions { get; } = [];

    /// <summary>
    /// Maps executor IDs to their output types (for proper deserialization during condition evaluation).
    /// </summary>
    public Dictionary<string, Type?> ExecutorOutputTypes { get; } = [];

    /// <summary>
    /// Gets or sets the starting executor ID for the workflow.
    /// </summary>
    public string StartExecutorId { get; set; } = string.Empty;
}
