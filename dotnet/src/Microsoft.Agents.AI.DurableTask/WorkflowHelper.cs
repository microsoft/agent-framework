// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents an executor in the workflow with its metadata.
/// </summary>
/// <param name="ExecutorId">The unique identifier of the executor.</param>
/// <param name="IsAgenticExecutor">Indicates whether this executor is an agentic executor.</param>
public sealed record WorkflowExecutorInfo(string ExecutorId, bool IsAgenticExecutor);

/// <summary>
/// Represents a level of executors that can be executed in parallel (Fan-Out).
/// All executors in the same level have their dependencies satisfied by previous levels.
/// </summary>
/// <param name="Level">The level number (0-based, starting from the root executor).</param>
/// <param name="Executors">The executors that can run in parallel at this level.</param>
/// <param name="IsFanIn">Indicates if this level is a Fan-In point (has executors with multiple predecessors).</param>
public sealed record WorkflowExecutionLevel(int Level, List<WorkflowExecutorInfo> Executors, bool IsFanIn);

/// <summary>
/// Represents the complete execution plan for a workflow, including parallel execution levels.
/// </summary>
public sealed class WorkflowExecutionPlan
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
    /// Gets whether this workflow has any parallel execution opportunities.
    /// </summary>
    public bool HasParallelism => this.Levels.Any(l => l.Executors.Count > 1);

    /// <summary>
    /// Gets whether this workflow has any Fan-In points.
    /// </summary>
    public bool HasFanIn => this.Levels.Any(l => l.IsFanIn);
}

/// <summary>
/// Provides helper methods for analyzing and executing workflows.
/// </summary>
public static class WorkflowHelper
{
    /// <summary>
    /// Accepts a workflow instance and returns a list of executors with metadata in the order they should be executed.
    /// </summary>
    /// <param name="workflow">The workflow instance to analyze.</param>
    /// <returns>A list of executor information in topological order (execution order).</returns>
    public static List<WorkflowExecutorInfo> GetExecutorsFromWorkflowInOrder(Workflow workflow)
    {
        WorkflowExecutionPlan plan = GetExecutionPlan(workflow);

        // Flatten the levels into a single list for backward compatibility
        List<WorkflowExecutorInfo> result = [];
        foreach (WorkflowExecutionLevel level in plan.Levels)
        {
            result.AddRange(level.Executors);
        }

        return result;
    }

    /// <summary>
    /// Analyzes the workflow and returns an execution plan that supports Fan-Out/Fan-In patterns.
    /// Executors at the same level can be executed in parallel (Fan-Out).
    /// Fan-In points are identified where multiple executors converge.
    /// </summary>
    /// <param name="workflow">The workflow instance to analyze.</param>
    /// <returns>An execution plan with parallel execution levels.</returns>
    public static WorkflowExecutionPlan GetExecutionPlan(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        Dictionary<string, ExecutorInfo> executors = workflow.ReflectExecutors();
        Dictionary<string, HashSet<EdgeInfo>> edges = workflow.ReflectEdges();

        WorkflowExecutionPlan plan = new();

        // Build adjacency lists (successors and predecessors)
        Dictionary<string, List<string>> successors = [];
        Dictionary<string, List<string>> predecessors = [];
        Dictionary<string, int> inDegree = [];

        // Initialize all executors
        foreach (string executorId in executors.Keys)
        {
            successors[executorId] = [];
            predecessors[executorId] = [];
            inDegree[executorId] = 0;
        }

        // Build the graph from edges
        foreach (KeyValuePair<string, HashSet<EdgeInfo>> edgeGroup in edges)
        {
            string sourceId = edgeGroup.Key;

            foreach (EdgeInfo edge in edgeGroup.Value)
            {
                foreach (string sinkId in edge.Connection.SinkIds)
                {
                    if (executors.ContainsKey(sinkId))
                    {
                        successors[sourceId].Add(sinkId);
                        predecessors[sinkId].Add(sourceId);
                        inDegree[sinkId]++;
                    }
                }
            }
        }

        // Store the graph structure in the plan
        foreach (string executorId in executors.Keys)
        {
            plan.Predecessors[executorId] = [.. predecessors[executorId]];
            plan.Successors[executorId] = [.. successors[executorId]];
        }

        // Build execution levels using modified Kahn's algorithm
        // Instead of processing one at a time, we process all nodes with in-degree 0 at once (same level)
        HashSet<string> processed = [];
        Dictionary<string, int> currentInDegree = new(inDegree);
        int levelNumber = 0;

        while (processed.Count < executors.Count)
        {
            // Find all executors that can be executed at this level (in-degree == 0 and not yet processed)
            List<string> currentLevelIds = [];

            foreach (KeyValuePair<string, int> kvp in currentInDegree)
            {
                if (kvp.Value == 0 && !processed.Contains(kvp.Key))
                {
                    currentLevelIds.Add(kvp.Key);
                }
            }

            // If no executors found but not all processed, there might be a cycle
            if (currentLevelIds.Count == 0)
            {
                // Add remaining unprocessed executors
                foreach (string executorId in executors.Keys)
                {
                    if (!processed.Contains(executorId))
                    {
                        currentLevelIds.Add(executorId);
                    }
                }

                if (currentLevelIds.Count == 0)
                {
                    break;
                }
            }

            // Check if this level is a Fan-In point (any executor has multiple predecessors)
            bool isFanIn = currentLevelIds.Any(id => predecessors[id].Count > 1);

            // Convert to WorkflowExecutorInfo
            List<WorkflowExecutorInfo> levelExecutors = [];
            foreach (string executorId in currentLevelIds)
            {
                processed.Add(executorId);

                if (executors.TryGetValue(executorId, out ExecutorInfo? executorInfo))
                {
                    bool isAgentic = IsAgentExecutorType(executorInfo.ExecutorType);
                    levelExecutors.Add(new WorkflowExecutorInfo(executorId, isAgentic));
                }

                // Decrement in-degree of all successors
                foreach (string successor in successors[executorId])
                {
                    currentInDegree[successor]--;
                }
            }

            plan.Levels.Add(new WorkflowExecutionLevel(levelNumber, levelExecutors, isFanIn));
            levelNumber++;
        }

        return plan;
    }

    /// <summary>
    /// Determines whether the specified executor type is an agentic executor.
    /// </summary>
    /// <param name="executorType">The executor type to check.</param>
    /// <returns><c>true</c> if the executor is an agentic executor; otherwise, <c>false</c>.</returns>
    internal static bool IsAgentExecutorType(TypeId executorType)
    {
        // hack for now. In the future, the MAF type could expose something which can help with this.
        // Check if the type name or assembly indicates it's an agent executor
        // This includes AgentRunStreamingExecutor, AgentExecutor, ChatClientAgent wrappers, etc.
        string typeName = executorType.TypeName;
        string assemblyName = executorType.AssemblyName;

        return typeName.Contains("AIAgentHostExecutor", StringComparison.OrdinalIgnoreCase) &&
                assemblyName.Contains("Microsoft.Agents.AI", StringComparison.OrdinalIgnoreCase);
    }
}
