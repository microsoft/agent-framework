// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.ObjectModel;

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
    /// <param name="cancellationToken">Cancellation token to observe while retrieving chat options.</param>
    public static async Task<ChatOptions?> GetChatOptionsAsync(this GptComponentMetadata promptAgent, RecalcEngine? engine, IList<AIFunction>? functions, CancellationToken cancellationToken = default)
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
            Temperature = modelOptions?.Temperature is { } temperature ? (float?)await temperature.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            MaxOutputTokens = modelOptions?.MaxOutputTokens is { } maxOutputTokens ? (int?)await maxOutputTokens.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            TopP = modelOptions?.TopP is { } topP ? (float?)await topP.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            TopK = modelOptions?.TopK is { } topK ? (int?)await topK.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            FrequencyPenalty = modelOptions?.FrequencyPenalty is { } frequencyPenalty ? (float?)await frequencyPenalty.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            PresencePenalty = modelOptions?.PresencePenalty is { } presencePenalty ? (float?)await presencePenalty.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            Seed = modelOptions?.Seed is { } seed ? (int?)await seed.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
            ResponseFormat = outputSchema?.AsChatResponseFormat(),
            ModelId = promptAgent.Model?.ModelNameHint,
            StopSequences = modelOptions?.StopSequences,
            AllowMultipleToolCalls = modelOptions?.AllowMultipleToolCalls is { } allowMultipleToolCalls ? await allowMultipleToolCalls.EvalAsync(engine, cancellationToken: cancellationToken).ConfigureAwait(false) : default,
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
