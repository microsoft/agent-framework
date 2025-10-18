// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="ModelOptions"/>.
/// </summary>
public static class ModelOptionsExtensions
{
    /// <summary>
    /// Retrieves the 'max_output_tokens' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static int? GetMaxOutputTokens(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return (int?)modelOptions.ExtensionData?.GetNumber("maxOutputTokens");
    }

    /// <summary>
    /// Retrieves the 'top_k' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static int? GetTopK(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return (int?)modelOptions.ExtensionData?.GetNumber("topK");
    }

    /// <summary>
    /// Retrieves the 'frequency_penalty' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static float? GetFrequencyPenalty(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return (float?)modelOptions.ExtensionData?.GetNumber("frequencyPenalty");
    }

    /// <summary>
    /// Retrieves the 'presence_penalty' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static float? GetPresencePenalty(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return (float?)modelOptions.ExtensionData?.GetNumber("presencePenalty");
    }

    /// <summary>
    /// Retrieves the 'seed' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static long? GetSeed(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return (long?)modelOptions.ExtensionData?.GetNumber("seed");
    }

    /// <summary>
    /// Retrieves the 'allow_multiple_tool_calls' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static bool? GetAllowMultipleToolCalls(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        return modelOptions.ExtensionData?.GetBoolean("allowMultipleToolCalls");
    }

    /*
    /// <summary>
    /// Retrieves the 'response_format' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static ChatResponseFormat? AsChatResponseFormat(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        var responseFormatValue = modelOptions.ExtensionData?.GetProperty<RecordDataValue>(InitializablePropertyPath.Create("responseFormat"));
        if (responseFormatValue is null)
        {
            return null;
        }

        return ChatResponseFormat.ForJsonSchema(
            schema: responseFormatValue.GetSchema() ?? throw new InvalidOperationException("Response format must include a JSON schema"),
            schemaName: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schemaName"))?.Value,
            schemaDescription: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schemaDescription"))?.Value);
    }
    */

    /// <summary>
    /// Retrieves the 'stop_sequence' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static IList<string>? GetStopSequences(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        var stopSequences = modelOptions.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("stopSequences"));
        if (stopSequences is not null)
        {
            return [.. stopSequences.Values.Select(ss => ss.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!).AsEnumerable()];
        }

        return null;
    }

    /// <summary>
    /// Retrieves the 'chat_tool_modelOptions' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    public static ChatToolMode? GetChatToolMode(this ModelOptions modelOptions)
    {
        Throw.IfNull(modelOptions);

        var mode = modelOptions.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("chatToolMode"))?.Value;
        if (mode is null)
        {
            return null;
        }

        return mode switch
        {
            "auto" => ChatToolMode.Auto,
            "none" => ChatToolMode.None,
            "require_any" => ChatToolMode.RequireAny,
            _ => ChatToolMode.RequireSpecific(mode),
        };
    }

    /// <summary>
    /// Retrieves the 'additional_properties' property from a <see cref="ModelOptions"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    /// <param name="excludedProperties">List of properties which should not be included in additional properties.</param>
    public static AdditionalPropertiesDictionary? GetAdditionalProperties(this ModelOptions modelOptions, string[] excludedProperties)
    {
        Throw.IfNull(modelOptions);

        var options = modelOptions.ExtensionData;
        if (options is null)
        {
            return null;
        }

        var additionalProperties = options.Properties
            .Where(kvp => !excludedProperties.Contains(kvp.Key))
            .ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToObject());

        if (additionalProperties is null || additionalProperties.Count == 0)
        {
            return null;
        }

        return new AdditionalPropertiesDictionary(additionalProperties);
    }
}
