// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows.Checkpointing;
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

        foreach (var workflow in this._options.Workflows)
        {
            this._logger.LogAddingWorkflowFunction(workflow.Key);

            //original.Add(CreateOrchestrationTrigger(workflow.Key));

            // We also want to create an HTTP trigger for this orchestration so users can start it via HTTP.
            this._logger.LogAddingHttpTrigger(workflow.Key);
            original.Add(CreateHttpTrigger(workflow.Key, $"workflows/{workflow.Key}/run"));

            // Create activity/entity functions for each executor in the workflow based on their type
            // Extract executor IDs from edges and start executor
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

            Dictionary<string, ExecutorInfo> executorInfos = workflow.Value.ReflectExecutors();

            foreach (string executorId in executorIds)
            {
                if (executorInfos.TryGetValue(executorId, out ExecutorInfo? executorInfo))
                {
                    // string functionName = $"{AgentSessionId.ToEntityName(workflow.Key)}-{executorId}"; //.Split("_")[0]
                    string functionName = $"{AgentSessionId.ToEntityName(workflow.Key)}-{executorId.Split("_")[0]}"; //.Split("_")[0]

                    // Check if the executor type is an agent-related type
                    if (IsAgentExecutorType(executorInfo.ExecutorType))
                    {
                        this._logger.LogAddingAgentEntityFunction(executorId, executorInfo.ExecutorType.TypeName, workflow.Key);
                        original.Add(CreateAgentTrigger(functionName));
                    }
                    else
                    {
                        this._logger.LogAddingActivityFunction(executorId, executorInfo.ExecutorType.TypeName, workflow.Key);
                        original.Add(CreateActivityTrigger(functionName));
                    }
                }
            }
        }

        this._logger.LogTransformFinished(original.Count);

        static bool IsAgentExecutorType(TypeId executorType)
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
            ],
            EntryPoint = BuiltInFunctions.InvokeWorkflowActivityFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }

    private static DefaultFunctionMetadata CreateAgentTrigger(string functionName)
    {
        return new DefaultFunctionMetadata()
        {
            Name = functionName,
            Language = "dotnet-isolated",
            RawBindings =
            [
                """{"name":"encodedEntityRequest","type":"entityTrigger","direction":"In"}""",
                """{"name":"client","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.RunAgentEntityFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }
}
