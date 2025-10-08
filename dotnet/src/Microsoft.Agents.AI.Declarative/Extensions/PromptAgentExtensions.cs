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
    /// Retrieves the 'kind' property from a <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    public static string? GetKindValue(this PromptAgent promptAgent)
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

        var outputSchema = promptAgent.OutputSchema;
        OpenAIResponsesModel? model = promptAgent.Model as OpenAIResponsesModel;
        var modelOptions = model?.Options;
        var tools = promptAgent.GetAITools();
        if (modelOptions is null && tools is null)
        {
            return null;
        }

        return new ChatOptions()
        {
            Instructions = promptAgent.AdditionalInstructions?.ToTemplateString(),
            Temperature = (float?)model?.Options?.Temperature.LiteralValue,
            MaxOutputTokens = modelOptions?.GetMaxOutputTokens(),
            TopP = (float?)modelOptions?.TopP.LiteralValue,
            TopK = modelOptions?.GetTopK(),
            FrequencyPenalty = modelOptions?.GetFrequencyPenalty(),
            PresencePenalty = modelOptions?.GetPresencePenalty(),
            Seed = modelOptions?.GetSeed(),
            ResponseFormat = outputSchema?.AsResponseFormat(),
            ModelId = model?.Id,
            StopSequences = modelOptions?.GetStopSequences(),
            AllowMultipleToolCalls = modelOptions?.GetAllowMultipleToolCalls(),
            ToolMode = modelOptions?.GetChatToolMode(),
            Tools = tools,
            AdditionalProperties = modelOptions?.GetAdditionalProperties(s_chatOptionProperties),
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
            var kind = tool.Kind.ToString();
            return kind switch
            {
                CodeInterpreterKind => tool.CreateCodeInterpreterTool(),
                FileSearchKind => tool.CreateFileSearchTool(),
                FunctionKind => tool.CreateFunctionDeclaration(),
                WebSearchKind => tool.CreateWebSearchTool(),
                McpKind => tool.CreateMcpTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {kind}, supported tool types are: {string.Join(",", s_validToolKinds)}"),
            };
        }).ToList() ?? [];
    }

    #region private
    private const string CodeInterpreterKind = "code_interpreter";
    private const string FileSearchKind = "file_search";
    private const string FunctionKind = "function";
    private const string WebSearchKind = "web_search";
    private const string McpKind = "mcp";

    private static readonly string[] s_validToolKinds =
    [
        CodeInterpreterKind,
        FileSearchKind,
        FunctionKind,
        WebSearchKind,
        McpKind
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
