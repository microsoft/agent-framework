// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI;
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
    /// <param name="agentCreationOptions">Instance of <see cref="AgentCreationOptions"/></param>
    public static ChatOptions? GetChatOptions(this PromptAgent promptAgent, AgentCreationOptions agentCreationOptions)
    {
        Throw.IfNull(promptAgent);

        var outputSchema = promptAgent.OutputSchema;
        OpenAIResponsesModel? model = promptAgent.Model as OpenAIResponsesModel;
        var modelOptions = model?.Options;
        var tools = promptAgent.GetAITools(agentCreationOptions.Tools);

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
    /// <param name="tools">Instance of <see cref="IList{AITool}"/></param>
    public static List<AITool>? GetAITools(this PromptAgent promptAgent, IList<AITool>? tools)
    {
        var promptTools = promptAgent.Tools.Select(tool =>
        {
            return tool switch
            {
                CodeInterpreterTool => ((CodeInterpreterTool)tool).CreateCodeInterpreterTool(),
                FunctionTool => ((FunctionTool)tool).CreateFunctionTool(tools),
                McpTool => ((McpTool)tool).CreateMcpTool(),
                FileSearchTool => ((FileSearchTool)tool).CreateFileSearchTool(),
                WebSearchTool => ((WebSearchTool)tool).CreateWebSearchTool(),
                _ => throw new NotSupportedException($"Unable to create tool definition because of unsupported tool type: {tool.Kind}, supported tool types are: {string.Join(",", s_validToolKinds)}"),
            };
        }).ToList() ?? [];

        return tools != null
            ? [.. promptTools, .. tools]
            : promptTools;
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
