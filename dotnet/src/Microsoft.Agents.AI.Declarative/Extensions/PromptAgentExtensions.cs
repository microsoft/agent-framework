// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="PromptAgent"/>.
/// </summary>
public static class PromptAgentExtensions
{
    /// <summary>
    /// Retrieves the 'type' property from a <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    public static string? GetTypeValue(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        try
        {
            var typeValue = promptAgent.ExtensionData?.GetProperty<StringDataValue>(InitializablePropertyPath.Create("type"));
            return typeValue?.Value;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>
    /// Retrieves the 'options' property from a <see cref="PromptAgent"/> as a <see cref="ChatOptions"/> instance.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    public static ChatOptions? GetChatOptions(this PromptAgent promptAgent)
    {
        Throw.IfNull(promptAgent);

        var aiSettings = promptAgent.AISettings;
        var tools = promptAgent.GetAITools();
        if (aiSettings is null && tools is null)
        {
            return null;
        }

        return new ChatOptions()
        {
            ConversationId = aiSettings?.ExtensionData?.GetString("conversation_id"),
            Instructions = promptAgent.AdditionalInstructions?.ToTemplateString(),
            Temperature = (float?)aiSettings?.ExtensionData?.GetNumber("temperature"),
            MaxOutputTokens = (int?)aiSettings?.ExtensionData?.GetNumber("max_output_tokens"),
            TopP = (float?)aiSettings?.ExtensionData?.GetNumber("top_p"),
            TopK = (int?)aiSettings?.ExtensionData?.GetNumber("top_k"),
            FrequencyPenalty = (float?)aiSettings?.ExtensionData?.GetNumber("frequency_penalty"),
            PresencePenalty = (float?)aiSettings?.ExtensionData?.GetNumber("presence_penalty"),
            Seed = (long?)aiSettings?.ExtensionData?.GetNumber("seed"),
            ResponseFormat = aiSettings?.GetResponseFormat(),
            ModelId = promptAgent.Model.Id,
            StopSequences = aiSettings?.GetStopSequences(),
            AllowMultipleToolCalls = aiSettings?.ExtensionData?.GetBoolean("allow_multiple_tool_calls"),
            ToolMode = aiSettings?.GetChatToolMode(),
            Tools = tools,
            AdditionalProperties = aiSettings?.GetAdditionalProperties(s_chatOptionProperties),
        };
    }

    /// <summary>
    /// Retrieves the 'tools' property from a <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    public static List<AITool>? GetAITools(this PromptAgent promptAgent)
    {
        return promptAgent.Tools.Select<AgentTool, AITool>(tool =>
        {
            var type = tool.ExtensionData?.GetString("type");
            return type switch
            {
                CodeInterpreterType => tool.CreateCodeInterpreterTool(),
                FileSearchType => tool.CreateFileSearchTool(),
                FunctionType => tool.CreateFunctionDeclaration(),
                WebSearchType => tool.CreateWebSearchTool(),
                McpType => tool.CreateMcpTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {type}, supported tool types are: {string.Join(",", s_validToolTypes)}"),
            };
        }).ToList() ?? [];
    }

    #region private
    private const string CodeInterpreterType = "code_interpreter";
    private const string FileSearchType = "file_search";
    private const string FunctionType = "function";
    private const string WebSearchType = "web_search";
    private const string McpType = "mcp";

    private static readonly string[] s_validToolTypes =
    [
        CodeInterpreterType,
        FileSearchType,
        FunctionType,
        WebSearchType,
        McpType
    ];

    private static readonly string[] s_chatOptionProperties =
[
    "allow_multiple_tool_calls",
        "conversation_id",
        "frequency_penalty",
        "instructions",
        "max_output_tokens",
        "model_id",
        "presence_penalty",
        "response_format",
        "seed",
        "stop_sequences",
        "temperature",
        "top_k",
        "top_p",
        "tool_mode",
        "tools",
    ];

    #endregion
}
