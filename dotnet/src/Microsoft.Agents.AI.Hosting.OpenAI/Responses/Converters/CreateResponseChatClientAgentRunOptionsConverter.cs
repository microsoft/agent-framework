// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

internal static class CreateResponseChatClientAgentRunOptionsConverter
{
    private static readonly JsonElement s_emptyJson = JsonElement.Parse("{}");

    public static ChatClientAgentRunOptions BuildOptions(this CreateResponse request)
    {
        ChatOptions chatOptions = new()
        {
            // The hosting layer owns response/conversation ids. Do not forward them
            // to the underlying IChatClient, which may use a different id model.
            Temperature = (float?)request.Temperature,
            TopP = (float?)request.TopP,
            MaxOutputTokens = request.MaxOutputTokens,
            Instructions = request.Instructions,
            ModelId = request.Model,
            AllowMultipleToolCalls = request.ParallelToolCalls,
        };

        if (request.ToolChoice is { } toolChoice)
        {
            chatOptions.ToolMode = toolChoice.ToChatToolMode();
        }

        if (request.Tools is { Count: > 0 })
        {
            List<AITool> tools = [];
            foreach (JsonElement tool in request.Tools)
            {
                if (tool.ToAITool() is { } aiTool)
                {
                    tools.Add(aiTool);
                }
            }

            if (tools.Count > 0)
            {
                chatOptions.Tools = tools;
            }
        }

        return new ChatClientAgentRunOptions(chatOptions);
    }

    private static AITool? ToAITool(this JsonElement tool)
    {
        if (tool.ValueKind != JsonValueKind.Object ||
            !tool.TryGetProperty("type", out JsonElement typeProperty) ||
            typeProperty.GetString() is not { } type)
        {
            return null;
        }

        if (string.Equals(type, "function", StringComparison.Ordinal))
        {
            return tool.ToAIFunctionDeclaration();
        }

        if (string.Equals(type, "custom", StringComparison.Ordinal) &&
            tool.TryGetToolName(out string? name))
        {
            return new ResponseCustomAITool(name, tool.TryGetStringProperty("description"));
        }

        return null;
    }

    private static AIFunctionDeclaration? ToAIFunctionDeclaration(this JsonElement tool)
    {
        JsonElement function = tool.TryGetProperty("function", out JsonElement functionProperty) &&
            functionProperty.ValueKind == JsonValueKind.Object
            ? functionProperty
            : tool;

        if (!function.TryGetToolName(out string? name))
        {
            return null;
        }

        JsonElement parameters = function.TryGetProperty("parameters", out JsonElement parametersProperty)
            ? parametersProperty
            : s_emptyJson;

        return AIFunctionFactory.CreateDeclaration(
            name,
            function.TryGetStringProperty("description"),
            parameters);
    }

    private static ChatToolMode? ToChatToolMode(this JsonElement toolChoice)
    {
        if (toolChoice.ValueKind == JsonValueKind.String)
        {
            return toolChoice.GetString() switch
            {
                "auto" => ChatToolMode.Auto,
                "none" => ChatToolMode.None,
                "required" => ChatToolMode.RequireAny,
                _ => null
            };
        }

        if (toolChoice.ValueKind != JsonValueKind.Object ||
            !toolChoice.TryGetProperty("type", out JsonElement typeProperty) ||
            typeProperty.GetString() is not { } type)
        {
            return null;
        }

        if (string.Equals(type, "allowed_tools", StringComparison.Ordinal))
        {
            return toolChoice.TryReadAllowedToolsMode();
        }

        return toolChoice.TryGetToolName(out string? name) ? ChatToolMode.RequireSpecific(name) : null;
    }

    private static ChatToolMode? TryReadAllowedToolsMode(this JsonElement toolChoice)
    {
        JsonElement modeSource = toolChoice;
        if (toolChoice.TryGetProperty("allowed_tools", out JsonElement allowedTools) &&
            allowedTools.ValueKind == JsonValueKind.Object)
        {
            modeSource = allowedTools;
        }

        if (!modeSource.TryGetProperty("mode", out JsonElement modeProperty))
        {
            return null;
        }

        return modeProperty.GetString() switch
        {
            "auto" => ChatToolMode.Auto,
            "required" => ChatToolMode.RequireAny,
            _ => null
        };
    }

    private static bool TryGetToolName(this JsonElement element, out string name)
    {
        if (element.TryGetProperty("name", out JsonElement nameProperty) &&
            nameProperty.ValueKind == JsonValueKind.String &&
            nameProperty.GetString() is { } directName)
        {
            name = directName;
            return true;
        }

        if (element.TryGetProperty("function", out JsonElement functionProperty) &&
            functionProperty.ValueKind == JsonValueKind.Object &&
            functionProperty.TryGetProperty("name", out JsonElement functionNameProperty) &&
            functionNameProperty.ValueKind == JsonValueKind.String &&
            functionNameProperty.GetString() is { } functionName)
        {
            name = functionName;
            return true;
        }

        if (element.TryGetProperty("custom", out JsonElement customProperty) &&
            customProperty.ValueKind == JsonValueKind.Object &&
            customProperty.TryGetProperty("name", out JsonElement customNameProperty) &&
            customNameProperty.ValueKind == JsonValueKind.String &&
            customNameProperty.GetString() is { } customName)
        {
            name = customName;
            return true;
        }

        name = string.Empty;
        return false;
    }

    private static string? TryGetStringProperty(this JsonElement element, string propertyName)
        => element.TryGetProperty(propertyName, out JsonElement property) &&
            property.ValueKind == JsonValueKind.String
            ? property.GetString()
            : null;

    private sealed class ResponseCustomAITool : AITool
    {
        public ResponseCustomAITool(string name, string? description)
        {
            this.Name = name;
            this.Description = description ?? string.Empty;
            this.AdditionalProperties = new Dictionary<string, object?>();
        }

        public override string Name { get; }

        public override string Description { get; }

        public override IReadOnlyDictionary<string, object?> AdditionalProperties { get; }
    }
}
