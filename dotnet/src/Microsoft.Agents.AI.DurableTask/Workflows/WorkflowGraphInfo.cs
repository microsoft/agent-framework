// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents the workflow graph structure needed for message-driven execution.
/// </summary>
/// <remarks>
/// <para>
/// This is a simplified representation that contains only the information needed
/// for routing messages between executors during superstep execution:
/// </para>
/// <list type="bullet">
/// <item><description>Successors for routing messages forward</description></item>
/// <item><description>Predecessors for detecting fan-in points</description></item>
/// <item><description>Edge conditions for conditional routing</description></item>
/// <item><description>Output types for deserialization during condition evaluation</description></item>
/// </list>
/// </remarks>
[DebuggerDisplay("Start = {StartExecutorId}, Executors = {Successors.Count}")]
internal sealed class WorkflowGraphInfo
{
    /// <summary>
    /// Gets or sets the starting executor ID for the workflow.
    /// </summary>
    public string StartExecutorId { get; set; } = string.Empty;

    /// <summary>
    /// Maps each executor ID to its successors (for message routing).
    /// </summary>
    public Dictionary<string, List<string>> Successors { get; } = [];

    /// <summary>
    /// Maps each executor ID to its predecessors (for fan-in detection).
    /// </summary>
    public Dictionary<string, List<string>> Predecessors { get; } = [];

    /// <summary>
    /// Maps edge connections (sourceId, targetId) to their condition functions.
    /// The condition function takes the predecessor's result and returns true if the edge should be followed.
    /// </summary>
    public Dictionary<(string SourceId, string TargetId), Func<object?, bool>?> EdgeConditions { get; } = [];

    /// <summary>
    /// Maps executor IDs to their output types (for proper deserialization during condition evaluation).
    /// </summary>
    public Dictionary<string, Type?> ExecutorOutputTypes { get; } = [];
}
