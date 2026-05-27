// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Transforms function metadata by dynamically registering Azure Functions triggers
/// for each configured durable workflow and its executors.
/// </summary>
/// <remarks>
/// For each workflow, this transformer registers:
/// <list type="bullet">
///   <item><description>An HTTP trigger function to start the workflow orchestration via HTTP.</description></item>
///   <item><description>An orchestration trigger function to run the workflow orchestration.</description></item>
///   <item><description>An activity trigger function for each non-agent executor in the workflow.</description></item>
///   <item><description>An entity trigger function for each AI agent executor in the workflow.</description></item>
/// </list>
/// When multiple workflows share the same executor, the corresponding function is registered only once.
/// </remarks>
internal sealed class DurableWorkflowsFunctionMetadataTransformer : IFunctionMetadataTransformer
{
    private readonly ILogger<DurableWorkflowsFunctionMetadataTransformer> _logger;
    private readonly FunctionsDurableOptions _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowsFunctionMetadataTransformer"/> class.
    /// </summary>
    /// <param name="logger">The logger instance for diagnostic output.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public DurableWorkflowsFunctionMetadataTransformer(
        ILogger<DurableWorkflowsFunctionMetadataTransformer> logger,
        FunctionsDurableOptions durableOptions)
    {
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        ArgumentNullException.ThrowIfNull(durableOptions);
        this._options = durableOptions;
    }

    /// <inheritdoc />
    public string Name => nameof(DurableWorkflowsFunctionMetadataTransformer);

    /// <inheritdoc />
    public void Transform(IList<IFunctionMetadata> original)
    {
        int initialCount = original.Count;
        this._logger.LogTransformingFunctionMetadata(initialCount);

        // Seed with existing function names to avoid duplicates across transformers
        // (e.g., when DurableAgentFunctionMetadataTransformer already registered entity triggers).
        HashSet<string> registeredFunctions = new(
            original.Select(f => f.Name!),
            StringComparer.OrdinalIgnoreCase);

        DurableWorkflowOptions workflowOptions = this._options.Workflows;
        foreach (var workflow in workflowOptions.Workflows)
        {
            string httpFunctionName = $"{BuiltInFunctions.HttpPrefix}{workflow.Key}";

            if (this._logger.IsEnabled(LogLevel.Information))
            {
                this._logger.LogInformation("Registering durable workflow functions for workflow '{WorkflowKey}' with HTTP trigger function name '{HttpFunctionName}'", workflow.Key, httpFunctionName);
            }

            // Register an orchestration function for the workflow.
            string orchestrationFunctionName = WorkflowNamingHelper.ToOrchestrationFunctionName(workflow.Key);
            if (registeredFunctions.Add(orchestrationFunctionName))
            {
                this._logger.LogRegisteringWorkflowTrigger(workflow.Key, orchestrationFunctionName, "orchestration");
                original.Add(FunctionMetadataFactory.CreateOrchestrationTrigger(
                    orchestrationFunctionName,
                    BuiltInFunctions.RunWorkflowOrchestrationFunctionEntryPoint));
            }

            // Register an HTTP trigger so users can start this workflow via HTTP.
            if (registeredFunctions.Add(httpFunctionName))
            {
                this._logger.LogRegisteringWorkflowTrigger(workflow.Key, httpFunctionName, "http");
                original.Add(FunctionMetadataFactory.CreateHttpTrigger(
                    workflow.Key,
                    $"workflows/{workflow.Key}/run",
                    BuiltInFunctions.RunWorkflowOrchestrationHttpFunctionEntryPoint));
            }

            // Register a status endpoint if opted in via AddWorkflow(exposeStatusEndpoint: true).
            if (this._options.IsStatusEndpointEnabled(workflow.Key))
            {
                string statusFunctionName = $"{BuiltInFunctions.HttpPrefix}{workflow.Key}-status";
                if (registeredFunctions.Add(statusFunctionName))
                {
                    this._logger.LogRegisteringWorkflowTrigger(workflow.Key, statusFunctionName, "http-status");
                    original.Add(FunctionMetadataFactory.CreateHttpTrigger(
                        $"{workflow.Key}-status",
                        $"workflows/{workflow.Key}/status/{{runId}}",
                        BuiltInFunctions.GetWorkflowStatusHttpFunctionEntryPoint,
                        methods: "\"get\""));
                }
            }

            // Register a respond endpoint when the workflow contains RequestPort nodes.
            bool hasRequestPorts = workflow.Value.ReflectExecutors().Values.Any(b => b is RequestPortBinding);
            if (hasRequestPorts)
            {
                string respondFunctionName = $"{BuiltInFunctions.HttpPrefix}{workflow.Key}-respond";
                if (registeredFunctions.Add(respondFunctionName))
                {
                    this._logger.LogRegisteringWorkflowTrigger(workflow.Key, respondFunctionName, "http-respond");
                    original.Add(FunctionMetadataFactory.CreateHttpTrigger(
                        $"{workflow.Key}-respond",
                        $"workflows/{workflow.Key}/respond/{{runId}}",
                        BuiltInFunctions.RespondToWorkflowHttpFunctionEntryPoint));
                }
            }

            // Register an MCP tool trigger if opted in via AddWorkflow(exposeMcpToolTrigger: true).
            if (this._options.IsMcpToolTriggerEnabled(workflow.Key))
            {
                string mcpToolFunctionName = $"{BuiltInFunctions.McpToolPrefix}{workflow.Key}";
                if (registeredFunctions.Add(mcpToolFunctionName))
                {
                    this._logger.LogRegisteringWorkflowTrigger(workflow.Key, mcpToolFunctionName, "mcpTool");
                    original.Add(FunctionMetadataFactory.CreateWorkflowMcpToolTrigger(workflow.Key, workflow.Value.Description));
                }
            }

            // Register activity or entity functions for each executor in the workflow.
            // ReflectExecutors() returns all executors across the graph; no need to manually traverse edges.
            foreach (KeyValuePair<string, ExecutorBinding> entry in workflow.Value.ReflectExecutors())
            {
                // Sub-workflow and RequestPort bindings use specialized dispatch, not activities.
                if (entry.Value is SubworkflowBinding or RequestPortBinding)
                {
                    continue;
                }

                string executorName = WorkflowNamingHelper.GetExecutorName(entry.Key);

                // AI agent executors are backed by durable entities; other executors use activity triggers.
                if (entry.Value is AIAgentBinding)
                {
                    string entityName = AgentSessionId.ToEntityName(executorName);
                    if (registeredFunctions.Add(entityName))
                    {
                        this._logger.LogRegisteringWorkflowTrigger(workflow.Key, entityName, "entity");
                        original.Add(FunctionMetadataFactory.CreateEntityTrigger(executorName));
                    }
                }
                else
                {
                    string functionName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);
                    if (registeredFunctions.Add(functionName))
                    {
                        this._logger.LogRegisteringWorkflowTrigger(workflow.Key, functionName, "activity");
                        original.Add(FunctionMetadataFactory.CreateActivityTrigger(functionName));
                    }
                }
            }
        }

        this._logger.LogTransformationComplete(original.Count - initialCount, original.Count);
    }
}
