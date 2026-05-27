// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Nodes;
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
    /// <param name="methods">The allowed HTTP methods as a JSON array fragment (e.g., <c>"\"get\""</c>). Defaults to POST.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an HTTP trigger.</returns>
    internal static DefaultFunctionMetadata CreateHttpTrigger(string name, string route, string entryPoint, string methods = "\"post\"")
    {
        return new DefaultFunctionMetadata()
        {
            Name = $"{BuiltInFunctions.HttpPrefix}{name}",
            Language = "dotnet-isolated",
            RawBindings =
            [
                $"{{\"name\":\"req\",\"type\":\"httpTrigger\",\"direction\":\"In\",\"authLevel\":\"function\",\"methods\": [{methods}],\"route\":\"{route}\"}}",
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

    /// <summary>
    /// Creates function metadata for an orchestration trigger function.
    /// </summary>
    /// <param name="functionName">The name of the orchestration function.</param>
    /// <param name="entryPoint">The entry point method for the orchestration trigger.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an orchestration trigger.</returns>
    internal static DefaultFunctionMetadata CreateOrchestrationTrigger(string functionName, string entryPoint)
    {
        return new DefaultFunctionMetadata()
        {
            Name = functionName,
            Language = "dotnet-isolated",
            RawBindings =
            [
                """{"name":"context","type":"orchestrationTrigger","direction":"In"}"""
            ],
            EntryPoint = entryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }

    /// <summary>
    /// Creates function metadata for an MCP tool trigger function that starts a workflow.
    /// </summary>
    /// <param name="workflowName">The name of the workflow to expose as an MCP tool.</param>
    /// <param name="description">An optional description for the MCP tool. If null, a default description is generated.</param>
    /// <returns>A <see cref="DefaultFunctionMetadata"/> configured for an MCP tool trigger.</returns>
    internal static DefaultFunctionMetadata CreateWorkflowMcpToolTrigger(
        string workflowName,
        string? description)
    {
        var functionName = $"{BuiltInFunctions.McpToolPrefix}{workflowName}";
        var toolDescription = description ?? $"Run the {workflowName} workflow";

        var toolProperties = new JsonArray(new JsonObject
        {
            ["propertyName"] = "input",
            ["propertyType"] = "string",
            ["description"] = "The input to the workflow.",
            ["isRequired"] = true,
            ["isArray"] = false,
        });

        var triggerBinding = new JsonObject
        {
            ["name"] = "context",
            ["type"] = "mcpToolTrigger",
            ["direction"] = "In",
            ["toolName"] = workflowName,
            ["description"] = toolDescription,
            ["toolProperties"] = toolProperties.ToJsonString(),
        };

        var inputBinding = new JsonObject
        {
            ["name"] = "input",
            ["type"] = "mcpToolProperty",
            ["direction"] = "In",
            ["propertyName"] = "input",
            ["description"] = "The input to the workflow",
            ["isRequired"] = true,
            ["dataType"] = "String",
            ["propertyType"] = "string",
        };

        var clientBinding = new JsonObject
        {
            ["name"] = "client",
            ["type"] = "durableClient",
            ["direction"] = "In",
        };

        return new DefaultFunctionMetadata
        {
            Name = functionName,
            Language = "dotnet-isolated",
            RawBindings = [triggerBinding.ToJsonString(), inputBinding.ToJsonString(), clientBinding.ToJsonString()],
            EntryPoint = BuiltInFunctions.RunWorkflowMcpToolFunctionEntryPoint,
            ScriptFile = BuiltInFunctions.ScriptFile,
        };
    }
}
