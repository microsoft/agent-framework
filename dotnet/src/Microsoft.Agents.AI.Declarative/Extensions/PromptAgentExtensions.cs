// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="GptComponentMetadata"/>.
/// </summary>
public static class PromptAgentExtensions
{
    /// <summary>
    /// Retrieves the 'options' property from a <see cref="GptComponentMetadata"/> as a <see cref="ChatOptions"/> instance.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="GptComponentMetadata"/></param>
    /// <param name="engine">Instance of <see cref="RecalcEngine"/></param>
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    public static ChatOptions? GetChatOptions(this GptComponentMetadata promptAgent, RecalcEngine? engine, IList<AIFunction>? functions)
    {
        Throw.IfNull(promptAgent);

        var outputSchema = promptAgent.OutputType;
        var modelOptions = promptAgent.Model?.Options;

        var tools = promptAgent.GetAITools(functions);

        if (modelOptions is null && tools is null)
        {
            return null;
        }

        return new ChatOptions()
        {
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            Temperature = (float?)modelOptions?.Temperature?.Eval(engine),
            MaxOutputTokens = (int?)modelOptions?.MaxOutputTokens?.Eval(engine),
            TopP = (float?)modelOptions?.TopP?.Eval(engine),
            TopK = (int?)modelOptions?.TopK?.Eval(engine),
            FrequencyPenalty = (float?)modelOptions?.FrequencyPenalty?.Eval(engine),
            PresencePenalty = (float?)modelOptions?.PresencePenalty?.Eval(engine),
            Seed = modelOptions?.Seed?.Eval(engine),
            ResponseFormat = outputSchema?.AsChatResponseFormat(),
            ModelId = promptAgent.Model?.ModelNameHint,
            StopSequences = modelOptions?.StopSequences,
            AllowMultipleToolCalls = modelOptions?.AllowMultipleToolCalls?.Eval(engine),
            ToolMode = modelOptions?.AsChatToolMode(),
            Tools = tools,
            AdditionalProperties = modelOptions?.GetAdditionalProperties(s_chatOptionProperties),
        };
    }

    /// <summary>
    /// Retrieves the 'tools' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Instance of <see cref="GptComponentMetadata"/></param>
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    internal static List<AITool>? GetAITools(this GptComponentMetadata promptAgent, IList<AIFunction>? functions)
    {
        return promptAgent.Tools.Select(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool => ((CodeInterpreterTool)tool).AsCodeInterpreterTool(),
                InvokeClientTaskAction => ((InvokeClientTaskAction)tool).CreateOrGetAITool(functions),
                McpServerTool => ((McpServerTool)tool).CreateHostedMcpTool(),
                FileSearchTool => ((FileSearchTool)tool).CreateFileSearchTool(),
                WebSearchTool => ((WebSearchTool)tool).CreateWebSearchTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}, supported tool types are: {string.Join(",", s_validToolKinds)}"),
            };
        }).ToList() ?? [];
    }

    #region private
    private const string CodeInterpreterKind = "codeInterpreter";
    private const string FileSearchKind = "fileSearch";
    private const string FunctionKind = "function";
    private const string WebSearchKind = "webSearch";
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
