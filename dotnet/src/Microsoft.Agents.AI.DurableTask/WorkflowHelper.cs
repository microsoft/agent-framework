// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents an executor in the workflow with its metadata.
/// </summary>
/// <param name="ExecutorId">The unique identifier of the executor.</param>
/// <param name="IsAgenticExecutor">Indicates whether this executor is an agentic executor.</param>
/// <param name="RequestPort">The request port if this executor is a request port executor; otherwise, null.</param>
public sealed record WorkflowExecutorInfo(string ExecutorId, bool IsAgenticExecutor, RequestPort? RequestPort = null)
{
    /// <summary>
    /// Gets a value indicating whether this executor is a request port executor (human-in-the-loop).
    /// </summary>
    public bool IsRequestPortExecutor => this.RequestPort is not null;
}

/// <summary>
/// Represents a level of executors that can be executed in parallel (Fan-Out).
/// All executors in the same level have their dependencies satisfied by previous levels.
/// </summary>
/// <param name="Level">The level number (0-based, starting from the root executor).</param>
/// <param name="Executors">The executors that can run in parallel at this level.</param>
/// <param name="IsFanIn">Indicates if this level is a Fan-In point (has executors with multiple predecessors).</param>
public sealed record WorkflowExecutionLevel(int Level, List<WorkflowExecutorInfo> Executors, bool IsFanIn);

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

        Dictionary<string, ExecutorBinding> executors = workflow.ReflectExecutors();
        Dictionary<string, HashSet<EdgeInfo>> edges = workflow.ReflectEdges();
        Dictionary<(string SourceId, string TargetId), Func<object?, bool>?> edgeConditions = workflow.ReflectEdgeConditions();

        WorkflowExecutionPlan plan = new();

        // Build adjacency lists (successors and predecessors)
        Dictionary<string, List<string>> successors = new(executors.Count);
        Dictionary<string, List<string>> predecessors = new(executors.Count);
        int[] inDegree = new int[executors.Count];
        Dictionary<string, int> executorIndex = new(executors.Count);

        // Initialize all executors and extract their output types
        int index = 0;
        foreach (KeyValuePair<string, ExecutorBinding> executor in executors)
        {
            executorIndex[executor.Key] = index++;
            successors[executor.Key] = [];
            predecessors[executor.Key] = [];

            // Extract output type from executor type (e.g., Executor<TInput, TOutput> -> TOutput)
            plan.ExecutorOutputTypes[executor.Key] = GetExecutorOutputType(executor.Value.ExecutorType);
        }

        // Build the graph from edges
        foreach (KeyValuePair<string, HashSet<EdgeInfo>> edgeGroup in edges)
        {
            string sourceId = edgeGroup.Key;
            List<string> sourceSuccessors = successors[sourceId];

            foreach (EdgeInfo edge in edgeGroup.Value)
            {
                foreach (string sinkId in edge.Connection.SinkIds)
                {
                    if (executorIndex.TryGetValue(sinkId, out int sinkIdx))
                    {
                        sourceSuccessors.Add(sinkId);
                        predecessors[sinkId].Add(sourceId);
                        inDegree[sinkIdx]++;
                    }
                }
            }
        }

        // Store edge conditions in the plan
        foreach (KeyValuePair<(string SourceId, string TargetId), Func<object?, bool>?> condition in edgeConditions)
        {
            plan.EdgeConditions[condition.Key] = condition.Value;
        }

        // Store the graph structure in the plan (reuse the built lists directly)
        foreach (string executorId in executors.Keys)
        {
            plan.Predecessors[executorId] = predecessors[executorId];
            plan.Successors[executorId] = successors[executorId];
        }

        // Build execution levels using queue-based Kahn's algorithm
        // Process all nodes with in-degree 0 at once (same level) for parallel execution
        Queue<string> currentLevel = new();
        foreach (KeyValuePair<string, int> kvp in executorIndex)
        {
            if (inDegree[kvp.Value] == 0)
            {
                currentLevel.Enqueue(kvp.Key);
            }
        }

        int levelNumber = 0;
        int processedCount = 0;

        while (currentLevel.Count > 0)
        {
            List<WorkflowExecutorInfo> levelExecutors = new(currentLevel.Count);
            Queue<string> nextLevel = new();
            bool isFanIn = false;

            while (currentLevel.Count > 0)
            {
                string executorId = currentLevel.Dequeue();
                processedCount++;

                ExecutorBinding executorBinding = executors[executorId];
                bool isAgentic = IsAgentExecutorType(executorBinding.ExecutorType);
                RequestPort? requestPort = (executorBinding is RequestPortBinding rpb) ? rpb.Port : null;
                levelExecutors.Add(new WorkflowExecutorInfo(executorId, isAgentic, requestPort));

                // Check Fan-In for this executor
                if (predecessors[executorId].Count > 1)
                {
                    isFanIn = true;
                }

                // Decrement in-degree of all successors and enqueue those ready for next level
                foreach (string successor in successors[executorId])
                {
                    int successorIdx = executorIndex[successor];
                    if (--inDegree[successorIdx] == 0)
                    {
                        nextLevel.Enqueue(successor);
                    }
                }
            }

            plan.Levels.Add(new WorkflowExecutionLevel(levelNumber, levelExecutors, isFanIn));
            levelNumber++;
            currentLevel = nextLevel;
        }

        // Handle cycle detection: if not all executors were processed, there's a cycle
        if (processedCount < executors.Count)
        {
            List<WorkflowExecutorInfo> remainingExecutors = [];
            foreach (KeyValuePair<string, ExecutorBinding> executor in executors)
            {
                if (inDegree[executorIndex[executor.Key]] > 0)
                {
                    bool isAgentic = IsAgentExecutorType(executor.Value.ExecutorType);
                    RequestPort? requestPort = (executor.Value is RequestPortBinding rpb) ? rpb.Port : null;
                    remainingExecutors.Add(new WorkflowExecutorInfo(executor.Key, isAgentic, requestPort));
                }
            }

            if (remainingExecutors.Count > 0)
            {
                bool isFanIn = remainingExecutors.Exists(e => predecessors[e.ExecutorId].Count > 1);
                plan.Levels.Add(new WorkflowExecutionLevel(levelNumber, remainingExecutors, isFanIn));
            }
        }

        return plan;
    }

    /// <summary>
    /// Determines whether the specified executor type is an agentic executor.
    /// </summary>
    /// <param name="executorType">The executor type to check.</param>
    /// <returns><c>true</c> if the executor is an agentic executor; otherwise, <c>false</c>.</returns>
    internal static bool IsAgentExecutorType(Type executorType)
    {
        // hack for now. In the future, the MAF type could expose something which can help with this.
        // Check if the type name or assembly indicates it's an agent executor
        // This includes AgentRunStreamingExecutor, AgentExecutor, ChatClientAgent wrappers, etc.
        string typeName = executorType.FullName ?? executorType.Name;
        string assemblyName = executorType.Assembly.GetName().Name ?? string.Empty;

        return typeName.Contains("AIAgentHostExecutor", StringComparison.OrdinalIgnoreCase) &&
                assemblyName.Contains("Microsoft.Agents.AI", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Extracts the output type from an executor type.
    /// For Executor&lt;TInput, TOutput&gt;, returns TOutput.
    /// For Executor&lt;TInput&gt;, returns null (void output).
    /// </summary>
    /// <param name="executorType">The executor type to analyze.</param>
    /// <returns>The output type, or null if the executor has no typed output.</returns>
    private static Type? GetExecutorOutputType(Type executorType)
    {
        // Walk up the inheritance chain to find Executor<TInput, TOutput> or Executor<TInput>
        Type? currentType = executorType;
        while (currentType is not null)
        {
            if (currentType.IsGenericType)
            {
                Type genericDefinition = currentType.GetGenericTypeDefinition();
                Type[] genericArgs = currentType.GetGenericArguments();

                // Check for Executor<TInput, TOutput> (2 type parameters)
                if (genericArgs.Length == 2 && genericDefinition.Name.StartsWith("Executor", StringComparison.Ordinal))
                {
                    return genericArgs[1]; // TOutput
                }

                // Check for Executor<TInput> (1 type parameter) - void return
                if (genericArgs.Length == 1 && genericDefinition.Name.StartsWith("Executor", StringComparison.Ordinal))
                {
                    return null;
                }
            }

            currentType = currentType.BaseType;
        }

        return null;
    }
}
