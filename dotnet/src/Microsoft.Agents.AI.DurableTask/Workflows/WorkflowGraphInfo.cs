// Copyright (c) Microsoft. All rights reserved.

// Example: Given this workflow graph with a fan-out from B and a fan-in at E,
// plus a conditional edge from B to D:
//
//     [A] ──► [B] ──► [C] ──► [E]
//              │               ▲
//              └──► [D] ──────┘
//                (condition:
//                 x => x.NeedsReview)
//
// WorkflowAnalyzer.BuildGraphInfo() produces:
//
//  StartExecutorId = "A"
//
//  Successors (who does each executor send output to?):
//  ┌──────────┬──────────────┐
//  │ "A"      │ ["B"]        │
//  │ "B"      │ ["C", "D"]   │  ◄── fan-out: B sends to both C and D
//  │ "C"      │ ["E"]        │
//  │ "D"      │ ["E"]        │
//  │ "E"      │ []           │  ◄── terminal: no successors
//  └──────────┴──────────────┘
//
//  Predecessors (who feeds into each executor?):
//  ┌──────────┬──────────────┐
//  │ "A"      │ []           │  ◄── start: no predecessors
//  │ "B"      │ ["A"]        │
//  │ "C"      │ ["B"]        │
//  │ "D"      │ ["B"]        │
//  │ "E"      │ ["C", "D"]   │  ◄── fan-in: count=2, messages will be aggregated
//  └──────────┴──────────────┘
//
//  EdgeConditions (which edges have routing conditions?):
//  ┌──────────────────┬──────────────────────────┐
//  │ ("B", "D")       │ x => x.NeedsReview       │  ◄── D only receives if condition is true
//  └──────────────────┴──────────────────────────┘
//  (The B→C edge has no condition, so C always receives B's output.)
//
//  ExecutorOutputTypes (what type does each executor return?):
//  ┌──────────┬──────────────────┐
//  │ "A"      │ typeof(string)   │  ◄── used by DurableDirectEdgeRouter to deserialize
//  │ "B"      │ typeof(Order)    │      the JSON message for condition evaluation
//  │ "C"      │ typeof(Report)   │
//  │ "D"      │ typeof(Report)   │
//  │ "E"      │ typeof(string)   │
//  └──────────┴──────────────────┘
//
// DurableEdgeMap then consumes this to build the runtime routing layer.

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
