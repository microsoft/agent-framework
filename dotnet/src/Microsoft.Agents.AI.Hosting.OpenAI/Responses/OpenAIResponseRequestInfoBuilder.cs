// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

internal static class OpenAIResponseRequestInfoBuilder
{
    public static OpenAIResponseRequestInfo ToRequestInfo(this CreateResponse request) => new()
    {
        Temperature = request.Temperature,
        TopP = request.TopP,
        MaxOutputTokens = request.MaxOutputTokens,
        Instructions = request.Instructions,
        Model = request.Model,
        Tools = request.Tools is { Count: > 0 } tools ? new List<JsonElement>(tools) : null,
        ToolChoice = request.ToolChoice?.ToChatToolMode(),
    };

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
