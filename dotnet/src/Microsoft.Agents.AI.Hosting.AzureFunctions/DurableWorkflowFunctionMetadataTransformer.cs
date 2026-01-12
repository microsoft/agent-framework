// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal sealed class DurableWorkflowFunctionMetadataTransformer : IFunctionMetadataTransformer
{
    private readonly ILogger<DurableWorkflowFunctionMetadataTransformer> _logger;
    private readonly DurableWorkflowOptions _options;

    public DurableWorkflowFunctionMetadataTransformer(ILogger<DurableWorkflowFunctionMetadataTransformer> logger, DurableWorkflowOptions durableWorkflowOptions)
    {
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        this._options = durableWorkflowOptions ?? throw new ArgumentNullException(nameof(durableWorkflowOptions));
    }

    public string Name => nameof(DurableWorkflowFunctionMetadataTransformer);

    public void Transform(IList<IFunctionMetadata> original)
    {
        if (this._logger.IsEnabled(LogLevel.Information))
        {
            this._logger.LogInformation("Transforming function metadata to add durable workflow functions. Initial function count: {FunctionCount}", original.Count);
        }

        foreach (var workflow in this._options.Workflows)
        {
            if (this._logger.IsEnabled(LogLevel.Information))
            {
                this._logger.LogInformation("Adding durable workflow function for workflow: {WorkflowName}", workflow.Key);
            }

            original.Add(CreateOrchestrationTrigger(workflow.Key));
            // We also want to create an HTTP trigge for this orchestration so users can start it via HTTP.
            if (this._logger.IsEnabled(LogLevel.Information))
            {
                this._logger.LogInformation("Adding HTTP trigger function for workflow: {WorkflowName}", workflow.Key);
                var httpTriggerMetadata = CreateHttpTrigger(workflow.Key, $"workflows/{workflow.Key}/run");
                original.Add(httpTriggerMetadata);
            }

            // Create activity functions for each executor in the workflow
            // Extract executor IDs from edges and start executor (since ExecutorBindings is internal)
            var executorIds = new HashSet<string> { workflow.Value.StartExecutorId };

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

            foreach (var executorId in executorIds)
            {
                if (this._logger.IsEnabled(LogLevel.Information))
                {
                    this._logger.LogInformation(
                        "Adding activity function for executor: {ExecutorId} in workflow: {WorkflowName}",
                        executorId,
                        workflow.Key);
                }

                original.Add(CreateActivityTrigger(workflow.Key, executorId));
            }
        }

        if (this._logger.IsEnabled(LogLevel.Information))
        {
            this._logger.LogInformation("Transform finished. Updated function count: {FunctionCount}", original.Count);
        }
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

    private static DefaultFunctionMetadata CreateOrchestrationTrigger(string name)
    {
        return new DefaultFunctionMetadata()
        {
            Name = AgentSessionId.ToEntityName(name),
            Language = "dotnet-isolated",
            RawBindings =
            [
               // """{"name":"context","type":"orchestrationTrigger","direction":"In"}""",
                """{"name":"taskOrchestrationContext","type":"orchestrationTrigger","direction":"In"}""",

            ],
            EntryPoint = BuiltInFunctions.RunWorkflowOrechstrtationFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }

    private static DefaultFunctionMetadata CreateActivityTrigger(string workflowName, string executorId)
    {
        string functionName = $"{AgentSessionId.ToEntityName(workflowName)}_{executorId}";

        return new DefaultFunctionMetadata()
        {
            Name = functionName,
            Language = "dotnet-isolated",
            RawBindings =
            [
                """{"name":"input","type":"activityTrigger","direction":"In","dataType":"String"}""",
            ],
            EntryPoint = BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }
}
