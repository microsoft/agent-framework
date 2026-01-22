// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal sealed class DurableWorkflowFunctionMetadataTransformer : IFunctionMetadataTransformer
{
    private readonly ILogger<DurableWorkflowFunctionMetadataTransformer> _logger;
    private readonly DurableWorkflowOptions _options;

    public DurableWorkflowFunctionMetadataTransformer(ILogger<DurableWorkflowFunctionMetadataTransformer> logger, DurableOptions durableOptions)
    {
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        ArgumentNullException.ThrowIfNull(durableOptions);
        this._options = durableOptions.Workflows;
    }

    public string Name => nameof(DurableWorkflowFunctionMetadataTransformer);

    public void Transform(IList<IFunctionMetadata> original)
    {
        this._logger.LogTransformStart(original.Count);

        // Track registered function names to avoid duplicates when the same executor is used in multiple workflows
        HashSet<string> registeredFunctionNames = new();

        foreach (var workflow in this._options.Workflows)
        {
            this._logger.LogAddingWorkflowFunction(workflow.Key);

            // Currently due to how durable executor is registered, we are not able to bind TaskOrechestrationContext parameter properly
            // because the InputBinding for TOC happens inside the DurableExecutor (rathen than in an input converter).
            // So for now, we are going to use single orchestration function for all workflows.
            //original.Add(CreateOrchestrationTrigger(workflow.Key));

            // We also want to create an HTTP trigger for this orchestration so users can start it via HTTP.
            this._logger.LogAddingHttpTrigger(workflow.Key);
            original.Add(CreateHttpTrigger(workflow.Key, $"workflows/{workflow.Key}/run"));

            // Check if MCP tool trigger is enabled for this workflow
            if (DurableWorkflowOptionsExtensions.TryGetWorkflowOptions(workflow.Key, out FunctionsWorkflowOptions? workflowOptions) &&
                workflowOptions?.McpToolTrigger.IsEnabled == true)
            {
                this._logger.LogAddingMcpToolTrigger(workflow.Key);
                original.Add(CreateMcpToolTrigger(workflow.Key, workflow.Value.Description));
            }

            // Create activity/entity functions for each executor in the workflow based on their type
            // Extract executor IDs from edges and start executor
            HashSet<string> executorIds = new() { workflow.Value.StartExecutorId };

            var reflectedEdges = workflow.Value.ReflectEdges();
            foreach (var (sourceId, edgeSet) in reflectedEdges)
            {
                executorIds.Add(sourceId);
                foreach (var edge in edgeSet)
                {
                    foreach (var sinkId in edge.Connection.SinkIds)
                    {
                        executorIds.Add(sinkId);
                    }
                }
            }

            Dictionary<string, ExecutorBinding> executorBindings = workflow.Value.ReflectExecutors();

            foreach (string executorId in executorIds)
            {
                if (executorBindings.TryGetValue(executorId, out ExecutorBinding? executorBinding))
                {
                    string executorName = WorkflowNamingHelper.GetExecutorName(executorId);
                    string functionName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

                    // Skip if this function has already been registered by another workflow
                    if (!registeredFunctionNames.Add(functionName))
                    {
                        this._logger.LogSkippingDuplicateFunction(functionName, workflow.Key);
                        continue;
                    }

                    // Check if the executor type is an agent-related type
                    if (WorkflowHelper.IsAgentExecutorType(executorBinding.ExecutorType))
                    {
                        this._logger.LogAddingAgentEntityFunction(executorId, executorBinding.ExecutorType.FullName ?? executorBinding.ExecutorType.Name, workflow.Key);
                        //original.Add(CreateAgentTrigger(functionName));
                    }
                    else
                    {
                        this._logger.LogAddingActivityFunction(executorId, executorBinding.ExecutorType.FullName ?? executorBinding.ExecutorType.Name, workflow.Key);
                        original.Add(CreateActivityTrigger(functionName));
                    }
                }
            }
        }

        this._logger.LogTransformFinished(original.Count);
    }

    private static DefaultFunctionMetadata CreateHttpTrigger(string name, string route)
    {
        return new DefaultFunctionMetadata()
        {
            Name = $"{BuiltInFunctions.HttpPrefix}{name}",
            Language = "dotnet-isolated",
            RawBindings =
            [
                $"{{\"name\":\"req\",\"type\":\"httpTrigger\",\"direction\":\"In\",\"authLevel\":\"function\",\"methods\": [\"post\"],\"route\":\"{route}\"}}",
                "{\"name\":\"$return\",\"type\":\"http\",\"direction\":\"Out\"}",
                "{\"name\":\"client\",\"type\":\"durableClient\",\"direction\":\"In\"}"
            ],
            EntryPoint = BuiltInFunctions.RunWorkflowOrechstrtationHttpFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile
        };
    }

    //private static DefaultFunctionMetadata CreateOrchestrationTrigger(string name)
    //{
    //    return new DefaultFunctionMetadata()
    //    {
    //        Name = AgentSessionId.ToEntityName(name),
    //        Language = "dotnet-isolated",
    //        RawBindings =
    //        [
    //           // """{"name":"context","type":"orchestrationTrigger","direction":"In"}""",
    //            """{"name":"taskOrchestrationContext","type":"orchestrationTrigger","direction":"In"}""",

    //        ],
    //        EntryPoint = BuiltInFunctions.RunWorkflowOrechstrtationFunctionEntryPoint,
    //        ScriptFile = BuiltInFunctions.ScriptFile,
    //    };
    //}

    private static DefaultFunctionMetadata CreateActivityTrigger(string functionName)
    {
        return new DefaultFunctionMetadata()
        {
            Name = functionName,
            Language = "dotnet-isolated",
            RawBindings =
            [
                """{"name":"input","type":"activityTrigger","direction":"In","dataType":"String"}""",
                """{"name":"durableTaskClient","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }

    private static DefaultFunctionMetadata CreateMcpToolTrigger(string workflowName, string? description)
    {
        return new DefaultFunctionMetadata
        {
            Name = $"{BuiltInFunctions.McpToolPrefix}{workflowName}",
            Language = "dotnet-isolated",
            RawBindings =
            [
                $$"""{"name":"context","type":"mcpToolTrigger","direction":"In","toolName":"{{workflowName}}","description":"{{description ?? $"Run the {workflowName} workflow"}}","toolProperties":"[{\"propertyName\":\"input\",\"propertyType\":\"string\",\"description\":\"The input to the workflow.\",\"isRequired\":true,\"isArray\":false}]"}""",
                """{"name":"input","type":"mcpToolProperty","direction":"In","propertyName":"input","description":"The input to the workflow","isRequired":true,"dataType":"String","propertyType":"string"}""",
                """{"name":"client","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.RunWorkflowMcpToolFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }
}
