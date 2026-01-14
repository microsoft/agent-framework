// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Represents an executor in the workflow with its metadata.
/// </summary>
/// <param name="ExecutorId">The unique identifier of the executor.</param>
/// <param name="IsAgenticExecutor">Indicates whether this executor is an agentic executor.</param>
internal sealed record WorkflowExecutorInfo(string ExecutorId, bool IsAgenticExecutor);

internal static class WorkflowHelper
{
    /// <summary>
    /// Accepts a workflow instance and returns a list of executors with metadata in the order they should be executed.
    /// </summary>
    /// <param name="workflow">The workflow instance to analyze.</param>
    /// <returns>A list of executor information in topological order (execution order).</returns>
    public static List<WorkflowExecutorInfo> GetExecutorsFromWorkflowInOrder(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        Dictionary<string, ExecutorInfo> executors = workflow.ReflectExecutors();
        Dictionary<string, HashSet<EdgeInfo>> edges = workflow.ReflectEdges();

        // Build adjacency list and in-degree map
        Dictionary<string, List<string>> adjacencyList = new();
        Dictionary<string, int> inDegree = new();

        // Initialize all executors with in-degree 0
        foreach (string executorId in executors.Keys)
        {
            adjacencyList[executorId] = new List<string>();
            inDegree[executorId] = 0;
        }

        // Build the graph from edges
        foreach (KeyValuePair<string, HashSet<EdgeInfo>> edgeGroup in edges)
        {
            string sourceId = edgeGroup.Key;

            foreach (EdgeInfo edge in edgeGroup.Value)
            {
                // For each sink (target) in this edge
                foreach (string sinkId in edge.Connection.SinkIds)
                {
                    // Add edge from source to sink
                    adjacencyList[sourceId].Add(sinkId);

                    // Increment in-degree of the sink
                    if (inDegree.TryGetValue(sinkId, out int currentDegree))
                    {
                        inDegree[sinkId] = currentDegree + 1;
                    }
                }
            }
        }

        // Perform topological sort using Kahn's algorithm
        List<string> orderedExecutorIds = new();
        Queue<string> queue = new();

        // Start with the workflow's starting executor
        queue.Enqueue(workflow.StartExecutorId);

        // Also add any other executors with in-degree 0 (shouldn't be any if workflow is well-formed)
        foreach (KeyValuePair<string, int> kvp in inDegree)
        {
            if (kvp.Value == 0 && kvp.Key != workflow.StartExecutorId)
            {
                queue.Enqueue(kvp.Key);
            }
        }

        while (queue.Count > 0)
        {
            string current = queue.Dequeue();
            orderedExecutorIds.Add(current);

            // For each neighbor of the current executor
            foreach (string neighbor in adjacencyList[current])
            {
                inDegree[neighbor]--;

                // If in-degree becomes 0, add to queue
                if (inDegree[neighbor] == 0)
                {
                    queue.Enqueue(neighbor);
                }
            }
        }

        // If result doesn't contain all executors, there might be a cycle or disconnected components
        if (orderedExecutorIds.Count != executors.Count)
        {
            // Add any remaining executors that weren't reached
            foreach (string executorId in executors.Keys)
            {
                if (!orderedExecutorIds.Contains(executorId))
                {
                    orderedExecutorIds.Add(executorId);
                }
            }
        }

        // Convert to WorkflowExecutorInfo with agentic executor detection
        List<WorkflowExecutorInfo> result = new();
        foreach (string executorId in orderedExecutorIds)
        {
            if (executors.TryGetValue(executorId, out ExecutorInfo? executorInfo))
            {
                bool isAgentic = IsAgentExecutorType(executorInfo.ExecutorType);
                result.Add(new WorkflowExecutorInfo(executorId, isAgentic));
            }
        }

        return result;
    }

    /// <summary>
    /// Determines whether the specified executor type is an agentic executor.
    /// </summary>
    /// <param name="executorType">The executor type to check.</param>
    /// <returns><c>true</c> if the executor is an agentic executor; otherwise, <c>false</c>.</returns>
    private static bool IsAgentExecutorType(TypeId executorType)
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
