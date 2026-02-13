// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides factory methods for creating common <see cref="DefaultFunctionMetadata"/> instances
/// used by function metadata transformers.
/// </summary>
internal static class FunctionMetadataFactory
{
    /// <summary>
    /// Creates function metadata for an entity trigger function.
    /// </summary>
    /// <param name="name">The base name used to derive the entity function name.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an entity trigger.</returns>
    internal static DefaultFunctionMetadata CreateEntityTrigger(string name)
    {
        return new DefaultFunctionMetadata()
        {
            Name = AgentSessionId.ToEntityName(name),
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

    /// <summary>
    /// Creates function metadata for an HTTP trigger function.
    /// </summary>
    /// <param name="name">The base name used to derive the HTTP function name.</param>
    /// <param name="route">The HTTP route for the trigger.</param>
    /// <param name="entryPoint">The entry point method for the HTTP trigger.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an HTTP trigger.</returns>
    internal static DefaultFunctionMetadata CreateHttpTrigger(string name, string route, string entryPoint)
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
            EntryPoint = entryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }

    /// <summary>
    /// Creates function metadata for an activity trigger function.
    /// </summary>
    /// <param name="functionName">The name of the activity function.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an activity trigger.</returns>
    internal static DefaultFunctionMetadata CreateActivityTrigger(string functionName)
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
}
