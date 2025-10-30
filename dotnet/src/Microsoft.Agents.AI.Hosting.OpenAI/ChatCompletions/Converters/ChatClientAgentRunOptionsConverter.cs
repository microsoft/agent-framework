// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Converters;

internal static class ChatClientAgentRunOptionsConverter
{
    private static readonly JsonElement s_emptyJson = JsonDocument.Parse("{}").RootElement;

    public static ChatClientAgentRunOptions BuildOptions(this CreateChatCompletion request)
    {
        ChatOptions chatOptions = new()
        {
            Temperature = request.Temperature,
            MaxOutputTokens = request.MaxCompletionTokens,
            FrequencyPenalty = request.FrequencyPenalty,
            PresencePenalty = request.PresencePenalty,
            Seed = request.Seed,
            TopP = request.TopP,
            StopSequences = request.Stop?.SequenceList ?? [],
            ResponseFormat = request.ResponseFormat?.ToChatResponseFormat()
        };

        if (request.ToolChoice is not null)
        {
            chatOptions.ToolMode = request.ToolChoice.ToChatToolMode();
        }

        if (request.Tools?.Count > 0)
        {
            chatOptions.Tools = request.Tools.Select(x => x.ToAITool()).ToList();
        }

        return new()
        {
            ChatOptions = chatOptions
        };
    }

    private static ChatResponseFormat ToChatResponseFormat(this ResponseFormat responseFormat)
    {
        if (responseFormat.IsText)
        {
            return ChatResponseFormat.Text;
        }
        if (responseFormat.IsJsonObject)
        {
            return ChatResponseFormat.Json;
        }
        if (responseFormat.IsJsonSchema)
        {
            var schema = responseFormat.JsonSchema.JsonSchema;
            return ChatResponseFormat.ForJsonSchema(schema.Schema, schema.Name, schema.Description);
        }

        throw new ArgumentOutOfRangeException(nameof(responseFormat));
    }

    private static AITool ToAITool(this Tool tool)
    {
        if (tool is FunctionTool functionTool)
        {
            var function = functionTool.Function;
            return AIFunctionFactory.CreateDeclaration(function.Name, function.Description, function.Parameters ?? s_emptyJson);
        }
        if (tool is CustomTool customTool)
        {
            var custom = customTool.Custom;
            return new CustomAITool(custom.Name, custom.Description, custom.Format?.AdditionalProperties);
        }

        throw new ArgumentOutOfRangeException(nameof(tool));
    }

    private static ChatToolMode? ToChatToolMode(this ToolChoice toolChoice)
    {
        if (toolChoice.IsMode)
        {
            return toolChoice.Mode switch
            {
                "auto" => ChatToolMode.Auto,
                "none" => ChatToolMode.None,
                "required" => ChatToolMode.RequireAny,
                _ => null
            };
        }

        if (toolChoice.IsAllowedTools)
        {
            var mode = toolChoice.AllowedTools.AllowedTools.Mode;
            return mode switch
            {
                "auto" => ChatToolMode.Auto,
                "required" => ChatToolMode.RequireAny,
                _ => null
            };
        }

        if (toolChoice.IsFunctionTool)
        {
            var function = toolChoice.FunctionTool.Function;
            return ChatToolMode.RequireSpecific(function.Name);
        }

        if (toolChoice.IsCustomTool)
        {
            var custom = toolChoice.CustomTool.Custom;
            return ChatToolMode.RequireSpecific(custom.Name);
        }

        throw new ArgumentOutOfRangeException(nameof(toolChoice));
    }
}
