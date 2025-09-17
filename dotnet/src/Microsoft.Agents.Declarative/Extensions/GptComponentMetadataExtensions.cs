// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="GptComponentMetadata"/>.
/// </summary>
/// <remarks>
/// These are temporary helper methods for use while the single agent definition is being added to Microsoft.Bot.ObjectModel.
/// </remarks>
public static class GptComponentMetadataExtensions
{
    /// <summary>
    /// Retrieves the 'type' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetTypeValue(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        try
        {
            var typeValue = element.ExtensionData?.GetProperty<StringDataValue>(InitializablePropertyPath.Create("type"));
            return typeValue?.Value;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>
    /// Retrieves the 'id' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetId(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var nameValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("id"));
        return nameValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'name' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetName(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var nameValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("name"));
        return nameValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'description' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string GetDescription(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var descriptionValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"));
        return descriptionValue?.Value ?? string.Empty;
    }

    /// <summary>
    /// Retrieves the 'tools' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static ImmutableArray<RecordDataValue> GetTools(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var toolsValue = element.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("tools"));
        return toolsValue?.Values ?? ImmutableArray<RecordDataValue>.Empty;
    }

    /// <summary>
    /// Retrieves the 'instructions' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetInstructions(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        return element.Instructions?.ToTemplateString();
    }

    /// <summary>
    /// Retrieves the 'options' property from a <see cref="GptComponentMetadata"/> as a <see cref="ChatOptions"/> instance.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static ChatOptions? GetChatOptions(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var chatOptionsValue = element.ExtensionData?.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("model.options"));
        if (chatOptionsValue is null)
        {
            return null;
        }

        return new ChatOptions()
        {
            ConversationId = chatOptionsValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("conversation_id"))?.Value,
            Instructions = chatOptionsValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("instructions"))?.Value,
            Temperature = (float?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("temperature"))?.Value,
            MaxOutputTokens = (int?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("max_output_tokens"))?.Value,
            TopP = (float?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("top_p"))?.Value,
            TopK = (int?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("top_k"))?.Value,
            FrequencyPenalty = (float?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("frequency_penalty"))?.Value,
            PresencePenalty = (float?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("presence_penalty"))?.Value,
            Seed = (long?)chatOptionsValue.GetPropertyOrNull<NumberDataValue>(InitializablePropertyPath.Create("seed"))?.Value,
            ResponseFormat = chatOptionsValue.GetResponseFormat(),
            ModelId = chatOptionsValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("model_id"))?.Value,
            StopSequences = chatOptionsValue.GetStopSequences(),
            AllowMultipleToolCalls = (bool?)chatOptionsValue.GetPropertyOrNull<BooleanDataValue>(InitializablePropertyPath.Create("allow_multiple_tool_calls"))?.Value,
            ToolMode = chatOptionsValue.GetChatToolMode(),
            Tools = element.GetAITools(),
            AdditionalProperties = chatOptionsValue.GetAdditionalProperties(),
        };
    }

    /// <summary>
    /// Retrieves the 'model.id' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetModelId(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var modelIdValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("model.id"));
        return modelIdValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'model.connection.endpoint' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetModelConnectionEndpoint(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var endpointValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("model.connection.endpoint"));
        return endpointValue?.Value;
    }

    // 
    /// <summary>
    /// Retrieves the 'model.connection.options.deployment_name' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetModelConnectionOptionsDeploymentName(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var deploymentNameValue = element.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("model.connection.options.deployment_name"));
        return deploymentNameValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'metadata' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static IReadOnlyDictionary<string, string>? GetMetadata(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        var metadataValue = element.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("metadata"));
        return metadataValue?.Values.Length > 0 ? metadataValue.Values[0].ToDictionary() : null;
    }

    /// <summary>
    /// Retrieves the 'tools' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static List<AITool>? GetAITools(this GptComponentMetadata element)
    {
        return element.GetTools().Select<RecordDataValue, AITool>(tool =>
        {
            var type = tool.GetTypeValue();
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
    #endregion
}
