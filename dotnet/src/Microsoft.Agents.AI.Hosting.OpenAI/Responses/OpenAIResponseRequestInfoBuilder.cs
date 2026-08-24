// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

internal static class OpenAIResponseRequestInfoBuilder
{
    private static readonly JsonElement s_emptyJson = JsonElement.Parse("{}");

    public static OpenAIResponseRequestInfo ToRequestInfo(this CreateResponse request) => new()
    {
        Temperature = request.Temperature,
        TopP = request.TopP,
        MaxOutputTokens = request.MaxOutputTokens,
        Instructions = request.Instructions,
        Model = request.Model,
        Tools = request.Tools is { Count: > 0 } tools ? new List<JsonElement>(tools) : null,
        FunctionTools = request.Tools?.ToFunctionTools(),
        ToolChoice = request.ToolChoice?.ToChatToolMode(),
    };

    private static List<AITool>? ToFunctionTools(this IReadOnlyList<JsonElement> tools)
    {
        List<AITool>? functionTools = null;

        foreach (JsonElement tool in tools)
        {
            if (tool.ToFunctionTool() is { } functionTool)
            {
                (functionTools ??= []).Add(functionTool);
            }
        }

        return functionTools;
    }

    private static AIFunctionDeclaration? ToFunctionTool(this JsonElement tool)
    {
        if (tool.ValueKind != JsonValueKind.Object ||
            !tool.TryGetProperty("type", out JsonElement type) ||
            type.ValueKind != JsonValueKind.String ||
            type.GetString() != "function" ||
            !tool.TryGetProperty("name", out JsonElement name) ||
            name.ValueKind != JsonValueKind.String ||
            name.GetString() is not { Length: > 0 } functionName)
        {
            return null;
        }

        JsonElement parameters = tool.TryGetProperty("parameters", out JsonElement requestParameters) &&
            requestParameters.ValueKind == JsonValueKind.Object
                ? requestParameters
                : s_emptyJson;

        string? description = tool.TryGetProperty("description", out JsonElement requestDescription) &&
            requestDescription.ValueKind == JsonValueKind.String
                ? requestDescription.GetString()
                : null;

        AIFunctionDeclaration function = AIFunctionFactory.CreateDeclaration(functionName, description, parameters);

        if (tool.TryGetProperty("strict", out JsonElement strict) &&
            strict.ValueKind is JsonValueKind.True or JsonValueKind.False)
        {
            function = new ResponseAIFunctionDeclaration(function, strict.GetBoolean());
        }

        return function;
    }

    private sealed class ResponseAIFunctionDeclaration : AIFunctionDeclaration
    {
        private readonly AIFunctionDeclaration _innerFunction;

        public ResponseAIFunctionDeclaration(AIFunctionDeclaration innerFunction, bool strict)
        {
            this._innerFunction = innerFunction;
            var additionalProperties = new Dictionary<string, object?>();
            foreach (KeyValuePair<string, object?> property in innerFunction.AdditionalProperties)
            {
                additionalProperties.Add(property.Key, property.Value);
            }

            additionalProperties["strict"] = strict;
            this.AdditionalProperties = additionalProperties;
        }

        public override string Name => this._innerFunction.Name;

        public override string Description => this._innerFunction.Description;

        public override JsonElement JsonSchema => this._innerFunction.JsonSchema;

        public override JsonElement? ReturnJsonSchema => this._innerFunction.ReturnJsonSchema;

        public override IReadOnlyDictionary<string, object?> AdditionalProperties { get; }
    }

    /// <summary>
    /// Maps an OpenAI Responses <c>tool_choice</c> value onto its <see cref="ChatToolMode"/> equivalent.
    /// </summary>
    /// <remarks>
    /// The Responses <c>tool_choice</c> is either a string (<c>none</c>, <c>auto</c> or <c>required</c>)
    /// or an object identifying a specific tool (for example <c>{ "type": "function", "name": "..." }</c>).
    /// Values that have no <see cref="ChatToolMode"/> equivalent are mapped to <see langword="null"/>.
    /// </remarks>
    private static ChatToolMode? ToChatToolMode(this JsonElement toolChoice)
    {
        switch (toolChoice.ValueKind)
        {
            case JsonValueKind.String:
                return toolChoice.GetString() switch
                {
                    "none" => ChatToolMode.None,
                    "auto" => ChatToolMode.Auto,
                    "required" => ChatToolMode.RequireAny,
                    _ => null
                };

            case JsonValueKind.Object:
                // Only a function tool selection (for example { "type": "function", "name": "..." })
                // has a ChatToolMode equivalent. Other object shapes (e.g. hosted tool selections) are
                // not mapped so that they are not mistaken for a specific function.
                if (toolChoice.TryGetProperty("type", out JsonElement type) && type.ValueKind == JsonValueKind.String &&
                    type.GetString() == "function" &&
                    toolChoice.TryGetProperty("name", out JsonElement name) && name.ValueKind == JsonValueKind.String &&
                    name.GetString() is { Length: > 0 } functionName)
                {
                    return ChatToolMode.RequireSpecific(functionName);
                }

                return null;

            default:
                return null;
        }
    }
}
