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
    /// Retrieves the 'options' property from a <see cref="PromptAgent"/> as a <see cref="ChatOptions"/> instance.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="PromptAgent"/></param>
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    public static ChatOptions? GetChatOptions(this PromptAgent promptAgent, IList<AIFunction>? functions)
    {
        Throw.IfNull(promptAgent);

        var outputSchema = promptAgent.OutputSchema;
        ChatModel? model = promptAgent.Model as ChatModel;
        var modelOptions = model?.Options;

        // TODO: Add logic to resolve tools for a service provider or from agent creation options
        var tools = promptAgent.GetAITools(functions);

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
            ResponseFormat = outputSchema?.AsChatResponseFormat(),
            ModelId = model?.Id?.LiteralValue,
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
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    public static List<AITool>? GetAITools(this PromptAgent promptAgent, IList<AIFunction>? functions)
    {
        return promptAgent.Tools.Select(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool => ((CodeInterpreterTool)tool).CreateCodeInterpreterTool(),
                FunctionTool => ((FunctionTool)tool).CreateFunctionTool(functions),
                McpTool => ((McpTool)tool).CreateMcpTool(),
                FileSearchTool => ((FileSearchTool)tool).CreateFileSearchTool(),
                WebSearchTool => ((WebSearchTool)tool).CreateWebSearchTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}, supported tool types are: {string.Join(",", s_validToolKinds)}"),
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
        "allowMultipleToolCalls",
        "conversationId",
        "chatToolMode",
        "frequencyPenalty",
        "additionalInstructions",
        "maxOutputTokens",
        "modelId",
        "presencePenalty",
        "responseFormat",
        "seed",
        "stopSequences",
        "temperature",
        "topK",
        "topP",
        "toolMode",
        "tools",
    ];

    #endregion
}
