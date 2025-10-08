// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="AISettings"/>.
/// </summary>
public static class AISettingsExtensions
{
    /// <summary>
    /// Retrieves the 'response_format' property from a <see cref="AISettings"/>.
    /// </summary>
    /// <param name="aiSettings">Instance of <see cref="AISettings"/></param>
    public static ChatResponseFormat? GetResponseFormat(this AISettings aiSettings)
    {
        Throw.IfNull(aiSettings);

        var responseFormatValue = aiSettings.ExtensionData?.GetProperty<RecordDataValue>(InitializablePropertyPath.Create("response_format"));
        if (responseFormatValue is null)
        {
            return null;
        }

        return ChatResponseFormat.ForJsonSchema(
            schema: responseFormatValue.GetSchema() ?? throw new InvalidOperationException("Response format must include a JSON schema"),
            schemaName: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schema_name"))?.Value,
            schemaDescription: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schema_description"))?.Value);
    }

    /// <summary>
    /// Retrieves the 'stop_sequence' property from a <see cref="AISettings"/>.
    /// </summary>
    /// <param name="aiSettings">Instance of <see cref="AISettings"/></param>
    public static IList<string>? GetStopSequences(this AISettings aiSettings)
    {
        Throw.IfNull(aiSettings);

        var stopSequences = aiSettings.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("stop_sequences"));
        if (stopSequences is not null)
        {
            return [.. stopSequences.Values.Select(ss => ss.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!).AsEnumerable()];
        }

        return null;
    }

    /// <summary>
    /// Retrieves the 'chat_tool_model' property from a <see cref="AISettings"/>.
    /// </summary>
    /// <param name="aiSettings">Instance of <see cref="AISettings"/></param>
    public static ChatToolMode? GetChatToolMode(this AISettings aiSettings)
    {
        Throw.IfNull(aiSettings);

        var mode = aiSettings.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("chat_tool_mode"))?.Value;
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
    /// Retrieves the 'additional_properties' property from a <see cref="AISettings"/>.
    /// </summary>
    /// <param name="aiSettings">Instance of <see cref="AISettings"/></param>
    /// <param name="excludedProperties">List of properties which should not be included in additional properties.</param>
    public static AdditionalPropertiesDictionary? GetAdditionalProperties(this AISettings aiSettings, string[] excludedProperties)
    {
        Throw.IfNull(aiSettings);

        var options = aiSettings.ExtensionData;
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
