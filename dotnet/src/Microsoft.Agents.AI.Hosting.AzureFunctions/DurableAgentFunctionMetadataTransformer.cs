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

#pragma warning disable IL3000 // Avoid accessing Assembly file path when publishing as a single file - Azure Functions does not use single-file publishing
    private static readonly string s_builtInFunctionsScriptFile = Path.GetFileName(typeof(BuiltInFunctions).Assembly.Location);
#pragma warning restore IL3000

    public DurableAgentFunctionMetadataTransformer(
        IReadOnlyDictionary<string, Func<IServiceProvider, AIAgent>> agents,
        ILogger<DurableAgentFunctionMetadataTransformer> logger)
    {
        this._agents = agents ?? throw new ArgumentNullException(nameof(agents));
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public string Name => nameof(DurableAgentFunctionMetadataTransformer);

    public void Transform(IList<IFunctionMetadata> original)
    {
        this._logger.LogInformation("Transforming function metadata to add durable agent functions. Initial function count: {FunctionCount}", original.Count);

        foreach (string agentName in this._agents.Keys)
        {
            this._logger.LogInformation("Registering functions for agent: {AgentName}", agentName);

            // Each agent type gets its own entity trigger function.
            // We do this 1:1 mapping for improved telemetry.
            original.Add(CreateAgentTrigger(agentName));

            // Each agent type gets its own HTTP trigger function.
            // TODO: Put this behind a configuration option.
            original.Add(CreateHttpTrigger(agentName, $"agents/{agentName}/run", nameof(BuiltInFunctions.RunAgentHttpAsync)));
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

    private static DefaultFunctionMetadata CreateHttpTrigger(string name, string route, string dotnetMethodName)
    {
        return new DefaultFunctionMetadata()
        {
            Name = $"{name}_http",
            Language = "dotnet-isolated",
            RawBindings =
            [
                $$"""{"name":"req","type":"httpTrigger","direction":"In","authLevel":"function","methods": ["post"],"route":"{{route}}"}""",
                """{"name":"$return","type":"http","direction":"Out"}""",
                """{"name":"client","type":"durableClient","direction":"In"}"""
            ],
            EntryPoint = BuiltInFunctions.RunAgentHttpFunctionEntryPoint,
            ScriptFile = s_builtInFunctionsScriptFile,
        };
    }
}
