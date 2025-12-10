// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Transforms function metadata by registering durable agent functions for each configured agent.
/// </summary>
/// <remarks>This transformer adds both entity trigger and HTTP trigger functions for every agent registered in the application.</remarks>
internal sealed class DurableAgentFunctionMetadataTransformer : IFunctionMetadataTransformer
{
    private readonly ILogger<DurableAgentFunctionMetadataTransformer> _logger;
    private readonly IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> _agents;
    private readonly IServiceProvider _serviceProvider;
    private readonly IFunctionsAgentOptionsProvider _functionsAgentOptionsProvider;

#pragma warning disable IL3000 // Avoid accessing Assembly file path when publishing as a single file - Azure Functions does not use single-file publishing
    private static readonly string s_builtInFunctionsScriptFile = Path.GetFileName(typeof(BuiltInFunctions).Assembly.Location);
#pragma warning restore IL3000

    public DurableAgentFunctionMetadataTransformer(
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agents,
        ILogger<DurableAgentFunctionMetadataTransformer> logger,
        IServiceProvider serviceProvider,
        IFunctionsAgentOptionsProvider functionsAgentOptionsProvider)
    {
        this._agents = agents ?? throw new ArgumentNullException(nameof(agents));
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        this._serviceProvider = serviceProvider ?? throw new ArgumentNullException(nameof(serviceProvider));
        this._functionsAgentOptionsProvider = functionsAgentOptionsProvider ?? throw new ArgumentNullException(nameof(functionsAgentOptionsProvider));
    }

    public string Name => nameof(DurableAgentFunctionMetadataTransformer);

    public void Transform(IList<IFunctionMetadata> original)
    {
        this._logger.LogTransformingFunctionMetadata(original.Count);

        foreach (KeyValuePair<string, Func<IServiceProvider, AIAgent>> kvp in this._agents)
        {
            string agentName = kvp.Key;

            this._logger.LogRegisteringTriggerForAgent(agentName, "entity");

            original.Add(CreateAgentTrigger(agentName));

            if (this._functionsAgentOptionsProvider.TryGet(agentName, out FunctionsAgentOptions? agentTriggerOptions))
            {
                if (agentTriggerOptions.HttpTrigger.IsEnabled)
                {
                    this._logger.LogRegisteringTriggerForAgent(agentName, "http");
                    original.Add(CreateHttpTrigger(agentName, $"agents/{agentName}/run"));
                }

                if (agentTriggerOptions.McpToolTrigger.IsEnabled)
                {
                    AIAgent agent = kvp.Value(this._serviceProvider);
                    this._logger.LogRegisteringTriggerForAgent(agentName, "mcpTool");
                    original.Add(CreateMcpToolTrigger(agentName, agent.Description));
                }
            }
        }
    }

    private static DefaultFunctionMetadata CreateAgentTrigger(string name)
    {
        return new DefaultFunctionMetadata()
        {
            Name = AgentSessionId.ToEntityName(name),
            Language = "dotnet-isolated",
            RawBindings =
            [
                """{"name":"dispatcher","type":"entityTrigger","direction":"In"}""",
                """{"name":"client","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.RunAgentEntityFunctionEntryPoint,
            ScriptFile = s_builtInFunctionsScriptFile,
        };
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
            EntryPoint = BuiltInFunctions.RunAgentHttpFunctionEntryPoint,
            ScriptFile = s_builtInFunctionsScriptFile,
        };
    }

    private static DefaultFunctionMetadata CreateMcpToolTrigger(string agentName, string? description)
    {
        return new DefaultFunctionMetadata
        {
            Name = $"{BuiltInFunctions.McpToolPrefix}{agentName}",
            Language = "dotnet-isolated",
            RawBindings =
            [
                $$"""{"name":"context","type":"mcpToolTrigger","direction":"In","toolName":"{{agentName}}","description":"{{description}}","toolProperties":"[{\"propertyName\":\"query\",\"propertyType\":\"string\",\"description\":\"The query to send to the agent.\",\"isRequired\":true,\"isArray\":false},{\"propertyName\":\"threadId\",\"propertyType\":\"string\",\"description\":\"Optional thread identifier.\",\"isRequired\":false,\"isArray\":false}]"}""",
                """{"name":"query","type":"mcpToolProperty","direction":"In","propertyName":"query","description":"The query to send to the agent","isRequired":true,"dataType":"String","propertyType":"string"}""",
                """{"name":"threadId","type":"mcpToolProperty","direction":"In","propertyName":"threadId","description":"The thread identifier.","isRequired":false,"dataType":"String","propertyType":"string"}""",
                """{"name":"client","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.RunAgentMcpToolFunctionEntryPoint,
            ScriptFile = s_builtInFunctionsScriptFile,
        };
    }
}
