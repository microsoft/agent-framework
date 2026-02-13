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
///   <item><description>An activity trigger function for each non-agent executor in the workflow.</description></item>
///   <item><description>An entity trigger function for each AI agent executor in the workflow.</description></item>
/// </list>
/// When multiple workflows share the same executor, the corresponding function is registered only once.
/// </remarks>
internal sealed class DurableWorkflowsFunctionMetadataTransformer : IFunctionMetadataTransformer
{
    private readonly ILogger<DurableWorkflowsFunctionMetadataTransformer> _logger;
    private readonly DurableWorkflowOptions _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowsFunctionMetadataTransformer"/> class.
    /// </summary>
    /// <param name="logger">The logger instance for diagnostic output.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public DurableWorkflowsFunctionMetadataTransformer(ILogger<DurableWorkflowsFunctionMetadataTransformer> logger, DurableOptions durableOptions)
    {
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        ArgumentNullException.ThrowIfNull(durableOptions);
        this._options = durableOptions.Workflows;
    }

    /// <inheritdoc />
    public string Name => nameof(DurableWorkflowsFunctionMetadataTransformer);

    /// <inheritdoc />
    public void Transform(IList<IFunctionMetadata> original)
    {
        this._logger.LogTransformingFunctionMetadata(original.Count);

        // Track registered function names to avoid duplicates when workflows share executors.
        HashSet<string> registeredFunctions = [];

        foreach (var workflow in this._options.Workflows)
        {
            string httpFunctionName = $"{BuiltInFunctions.HttpPrefix}{workflow.Key}";

            if (this._logger.IsEnabled(LogLevel.Information))
            {
                this._logger.LogInformation("Registering durable workflow functions for workflow '{WorkflowKey}' with HTTP trigger function name '{HttpFunctionName}'", workflow.Key, httpFunctionName);
            }

            // NOTE: Per-workflow orchestration function metadata is not registered here. The
            // TaskOrchestrationContext binding happens inside the DurableExecutor rather than
            // through an input converter or middleware, so a single shared orchestration
            // function is used for all workflows instead.

            // Register an HTTP trigger so users can start this workflow via HTTP.
            if (registeredFunctions.Add(httpFunctionName))
            {
                original.Add(FunctionMetadataFactory.CreateHttpTrigger(workflow.Key, $"workflows/{workflow.Key}/run", BuiltInFunctions.RunWorkflowOrchestrationHttpFunctionEntryPoint));
            }

            // Register activity or entity functions for each executor in the workflow.
            // ReflectExecutors() returns all executors across the graph; no need to manually traverse edges.
            foreach (KeyValuePair<string, ExecutorBinding> entry in workflow.Value.ReflectExecutors())
            {
                // Sub-workflow bindings are handled as separate orchestrations, not activities.
                if (entry.Value is SubworkflowBinding)
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
                        original.Add(FunctionMetadataFactory.CreateEntityTrigger(executorName));
                    }
                }
                else
                {
                    string functionName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);
                    if (registeredFunctions.Add(functionName))
                    {
                        original.Add(FunctionMetadataFactory.CreateActivityTrigger(functionName));
                    }
                }
            }
        }
    }
}
