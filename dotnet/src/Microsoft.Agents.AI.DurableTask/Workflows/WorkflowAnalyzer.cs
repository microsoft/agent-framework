// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Analyzes workflow structure to extract executor metadata and build graph information
/// for message-driven execution.
/// </summary>
internal static class WorkflowAnalyzer
{
    private const string AgentExecutorTypeName = "AIAgentHostExecutor";
    private const string AgentAssemblyPrefix = "Microsoft.Agents.AI";
    private const string ExecutorTypePrefix = "Executor";

    /// <summary>
    /// Analyzes a workflow instance and returns a list of executors with their metadata.
    /// </summary>
    /// <param name="workflow">The workflow instance to analyze.</param>
    /// <returns>A list of executor information in workflow order.</returns>
    internal static List<WorkflowExecutorInfo> GetExecutorsFromWorkflowInOrder(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        return workflow.ReflectExecutors()
            .Select(kvp => CreateExecutorInfo(kvp.Key, kvp.Value))
            .ToList();
    }

    /// <summary>
    /// Builds the workflow graph information needed for message-driven execution.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Extracts routing information including successors, predecessors, edge conditions,
    /// and output types. Supports cyclic workflows through message-driven superstep execution.
    /// </para>
    /// <para>
    /// The returned <see cref="WorkflowGraphInfo"/> is consumed by <c>DurableEdgeMap</c>
    /// to build the runtime routing layer:
    /// <c>Successors</c> become <c>IDurableEdgeRouter</c> instances,
    /// <c>Predecessors</c> become fan-in counts, and
    /// <c>EdgeConditions</c> / <c>ExecutorOutputTypes</c> are passed into
    /// <c>DurableDirectEdgeRouter</c> for conditional routing with typed deserialization.
    /// </para>
    /// </remarks>
    /// <param name="workflow">The workflow instance to analyze.</param>
    /// <returns>A graph info object containing routing information.</returns>
    internal static WorkflowGraphInfo BuildGraphInfo(Workflow workflow)
    {
        ArgumentNullException.ThrowIfNull(workflow);

        Dictionary<string, ExecutorBinding> executors = workflow.ReflectExecutors();

        WorkflowGraphInfo graphInfo = new()
        {
            StartExecutorId = workflow.StartExecutorId
        };

        InitializeExecutorMappings(graphInfo, executors);
        PopulateGraphFromEdges(graphInfo, workflow.Edges);

        return graphInfo;
    }

    /// <summary>
    /// Determines whether the specified executor type is an agentic executor.
    /// </summary>
    /// <param name="executorType">The executor type to check.</param>
    /// <returns><c>true</c> if the executor is an agentic executor; otherwise, <c>false</c>.</returns>
    internal static bool IsAgentExecutorType(Type executorType)
    {
        string typeName = executorType.FullName ?? executorType.Name;
        string assemblyName = executorType.Assembly.GetName().Name ?? string.Empty;

        return typeName.Contains(AgentExecutorTypeName, StringComparison.OrdinalIgnoreCase)
            && assemblyName.Contains(AgentAssemblyPrefix, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Creates a <see cref="WorkflowExecutorInfo"/> from an executor binding.
    /// </summary>
    /// <param name="executorId">The unique identifier of the executor.</param>
    /// <param name="binding">The executor binding containing type and configuration information.</param>
    /// <returns>A new <see cref="WorkflowExecutorInfo"/> instance with extracted metadata.</returns>
    private static WorkflowExecutorInfo CreateExecutorInfo(string executorId, ExecutorBinding binding)
    {
        bool isAgentic = IsAgentExecutorType(binding.ExecutorType);
        RequestPort? requestPort = (binding is RequestPortBinding rpb) ? rpb.Port : null;
        Workflow? subWorkflow = (binding is SubworkflowBinding swb) ? swb.WorkflowInstance : null;

        return new WorkflowExecutorInfo(executorId, isAgentic, requestPort, subWorkflow);
    }

    /// <summary>
    /// Initializes the graph info with empty collections for each executor.
    /// </summary>
    /// <param name="graphInfo">The graph info to initialize.</param>
    /// <param name="executors">The dictionary of executor bindings.</param>
    private static void InitializeExecutorMappings(WorkflowGraphInfo graphInfo, Dictionary<string, ExecutorBinding> executors)
    {
        foreach ((string executorId, ExecutorBinding binding) in executors)
        {
            graphInfo.Successors[executorId] = [];
            graphInfo.Predecessors[executorId] = [];
            graphInfo.ExecutorOutputTypes[executorId] = GetExecutorOutputType(binding.ExecutorType);
        }
    }

    /// <summary>
    /// Populates the graph info with successor/predecessor relationships and edge conditions.
    /// </summary>
    /// <param name="graphInfo">The graph info to populate.</param>
    /// <param name="edges">The dictionary of edges grouped by source executor ID.</param>
    private static void PopulateGraphFromEdges(WorkflowGraphInfo graphInfo, Dictionary<string, HashSet<Edge>> edges)
    {
        foreach ((string sourceId, HashSet<Edge> edgeSet) in edges)
        {
            List<string> successors = graphInfo.Successors[sourceId];

            foreach (Edge edge in edgeSet)
            {
                AddSuccessorsFromEdge(graphInfo, sourceId, edge, successors);
                TryAddEdgeCondition(graphInfo, edge);
            }
        }
    }

    /// <summary>
    /// Adds successor relationships from an edge to the graph info.
    /// </summary>
    /// <param name="graphInfo">The graph info to update.</param>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="edge">The edge containing connection information.</param>
    /// <param name="successors">The list of successors to append to.</param>
    private static void AddSuccessorsFromEdge(
        WorkflowGraphInfo graphInfo,
        string sourceId,
        Edge edge,
        List<string> successors)
    {
        foreach (string sinkId in edge.Data.Connection.SinkIds)
        {
            if (!graphInfo.Successors.ContainsKey(sinkId))
            {
                continue;
            }

            successors.Add(sinkId);
            graphInfo.Predecessors[sinkId].Add(sourceId);
        }
    }

    /// <summary>
    /// Extracts and adds an edge condition to the graph info if present.
    /// </summary>
    /// <param name="graphInfo">The graph info to update.</param>
    /// <param name="edge">The edge that may contain a condition.</param>
    private static void TryAddEdgeCondition(WorkflowGraphInfo graphInfo, Edge edge)
    {
        DirectEdgeData? directEdge = edge.DirectEdgeData;

        if (directEdge?.Condition is not null)
        {
            graphInfo.EdgeConditions[(directEdge.SourceId, directEdge.SinkId)] = directEdge.Condition;
        }
    }

    /// <summary>
    /// Extracts the output type from an executor type by walking the inheritance chain.
    /// </summary>
    /// <param name="executorType">The executor type to analyze.</param>
    /// <returns>
    /// The TOutput type for Executor&lt;TInput, TOutput&gt;,
    /// or <c>null</c> for Executor&lt;TInput&gt; (void output) or non-executor types.
    /// </returns>
    private static Type? GetExecutorOutputType(Type executorType)
    {
        Type? currentType = executorType;

        while (currentType is not null)
        {
            Type? outputType = TryExtractOutputTypeFromGeneric(currentType);
            if (outputType is not null || IsVoidExecutorType(currentType))
            {
                return outputType;
            }

            currentType = currentType.BaseType;
        }

        return null;
    }

    /// <summary>
    /// Attempts to extract the output type from a generic executor type.
    /// </summary>
    /// <param name="type">The type to inspect.</param>
    /// <returns>The TOutput type if this is an Executor&lt;TInput, TOutput&gt;; otherwise, <c>null</c>.</returns>
    private static Type? TryExtractOutputTypeFromGeneric(Type type)
    {
        if (!type.IsGenericType)
        {
            return null;
        }

        Type genericDefinition = type.GetGenericTypeDefinition();
        Type[] genericArgs = type.GetGenericArguments();

        bool isExecutorType = genericDefinition.Name.StartsWith(ExecutorTypePrefix, StringComparison.Ordinal);
        if (!isExecutorType)
        {
            return null;
        }

        // Executor<TInput, TOutput> - return TOutput
        if (genericArgs.Length == 2)
        {
            return genericArgs[1];
        }

        return null;
    }

    /// <summary>
    /// Determines whether the type is a void-returning executor (Executor&lt;TInput&gt;).
    /// </summary>
    /// <param name="type">The type to check.</param>
    /// <returns><c>true</c> if this is an Executor with a single type parameter; otherwise, <c>false</c>.</returns>
    private static bool IsVoidExecutorType(Type type)
    {
        if (!type.IsGenericType)
        {
            return false;
        }

        Type genericDefinition = type.GetGenericTypeDefinition();
        Type[] genericArgs = type.GetGenericArguments();

        // Executor<TInput> with 1 type parameter indicates void return
        return genericArgs.Length == 1
            && genericDefinition.Name.StartsWith(ExecutorTypePrefix, StringComparison.Ordinal);
    }
}
