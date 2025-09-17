// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataValue"/> and <see cref="RecordDataValue"/>.
/// </summary>
public static class RecordDataValueExtensions
{
    /// <summary>
    /// Converts a <see cref="RecordDataValue"/> to a <see cref="IReadOnlyDictionary{TKey, TValue}"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static IReadOnlyDictionary<string, string> ToDictionary(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        return recordData.Properties.ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToString() ?? string.Empty
        );
    }

    /// <summary>
    /// Retrieves the 'type' property from a <see cref="RecordDataValue"/>
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static string? GetTypeValue(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var typeValue = recordData.GetProperty<StringDataValue>(InitializablePropertyPath.Create("type"));
        return typeValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'name' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static string? GetName(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var nameValue = recordData.GetProperty<StringDataValue>(InitializablePropertyPath.Create("name"));
        return nameValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'description' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static string? GetDescription(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var descriptionValue = recordData.GetProperty<StringDataValue>(InitializablePropertyPath.Create("description"));
        return descriptionValue?.Value;
    }

    /// <summary>
    /// Retrieves the 'response_format' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static ChatResponseFormat? GetResponseFormat(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var responseFormatValue = recordData.GetProperty<RecordDataValue>(InitializablePropertyPath.Create("response_format"));
        if (responseFormatValue is null)
        {
            return null;
        }

        return ChatResponseFormat.ForJsonSchema(
            schema: responseFormatValue.GetSchema(),
            schemaName: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schema_name"))?.Value,
            schemaDescription: responseFormatValue.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schema_description"))?.Value);
    }

    /// <summary>
    /// Retrieves the 'schema' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    public static JsonElement GetSchema(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        try
        {
            var schemaStr = recordData.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("json_schema.schema"));
            if (schemaStr?.Value is not null)
            {
                return JsonSerializer.Deserialize<JsonElement>(schemaStr.Value);
            }
        }
        catch (InvalidCastException)
        {
            // Ignore and try next
        }

        var responseFormRec = recordData.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("json_schema.schema"));
        if (responseFormRec is not null)
        {
            var json = JsonSerializer.Serialize(responseFormRec, ElementSerializer.CreateOptions());
            return JsonSerializer.Deserialize<JsonElement>(json);
        }

        throw new InvalidOperationException("Response format must include a JSON schema");
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

    /// <summary>
    /// Retrieves the 'stop_sequence' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static IList<string>? GetStopSequences(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var stopSequences = recordData.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("stop_sequences"));
        if (stopSequences is not null)
        {
            return [.. stopSequences.Values.Select(ss => ss.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!).AsEnumerable()];
        }

        return null;
    }

    /// <summary>
    /// Retrieves the 'chat_tool_model' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static ChatToolMode? GetChatToolMode(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var mode = recordData.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("chat_tool_mode"))?.Value;
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
    /// Retrieves the 'additional_properties' property from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="recordData">Instance of <see cref="RecordDataValue"/></param>
    public static AdditionalPropertiesDictionary? GetAdditionalProperties(this RecordDataValue recordData)
    {
        Throw.IfNull(recordData);

        var options = recordData.GetPropertyOrNull<RecordDataValue>(InitializablePropertyPath.Create("options"));
        if (options is null)
        {
            return null;
        }

        var additionalProperties = recordData.Properties
            .Where(kvp => !s_chatOptionProperties.Contains(kvp.Key))
            .ToDictionary(
            kvp => kvp.Key,
            kvp => kvp.Value?.ToObject());

        if (additionalProperties is null || additionalProperties.Count == 0)
        {
            return null;
        }

        return new AdditionalPropertiesDictionary(additionalProperties);
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="RecordDataValue"/></param>
    internal static HostedCodeInterpreterTool CreateCodeInterpreterTool(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new HostedCodeInterpreterTool();
    }

    /// <summary>
    /// Retrieves the 'function' tool from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="RecordDataValue"/></param>
    internal static AIFunctionDeclaration CreateFunctionDeclaration(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        string? name = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("name"))?.Value;
        Throw.IfNull(name);
        string? description = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("description"))?.Value;

        var jsonSchema = tool.GetSchema();

        return AIFunctionFactory.CreateDeclaration(
            name: name,
            description: description,
            jsonSchema: jsonSchema);
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="RecordDataValue"/></param>
    internal static HostedFileSearchTool CreateFileSearchTool(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new HostedFileSearchTool();
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="RecordDataValue"/></param>
    internal static HostedWebSearchTool CreateWebSearchTool(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        return new HostedWebSearchTool();
    }

    /// <summary>
    /// Retrieves the 'code-interpreter' tool from a <see cref="RecordDataValue"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="RecordDataValue"/></param>
    internal static HostedMcpServerTool CreateMcpTool(this RecordDataValue tool)
    {
        Throw.IfNull(tool);

        string? serverName = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("server_name"))?.Value;
        Throw.IfNull(serverName);
        string? serverUrl = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("server_url"))?.Value;
        Throw.IfNull(serverUrl);

        var serverDescription = tool.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("server_description"))?.Value;
        var allowedTools = tool.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("allowed_tools"))?.Values
            .Select(t => t.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("Value"))?.Value!)
            .Where(t => !string.IsNullOrWhiteSpace(t))
            .ToList();

        return new HostedMcpServerTool(serverName, serverUrl)
        {
            ServerDescription = serverDescription,
            AllowedTools = allowedTools,
            // TODO: add support for these properties
            // ApprovalMode =
            // Headers =
        };
    }

    #region private
    internal static object? ToObject(this DataValue? value)
    {
        if (value is null)
        {
            return null;
        }
        return value switch
        {
            StringDataValue s => s.Value,
            NumberDataValue n => n.Value,
            BooleanDataValue b => b.Value,
            TableDataValue t => t.Values.Select(v => v.ToObject()).ToList(),
            RecordDataValue r => r.Properties.ToDictionary(kvp => kvp.Key, kvp => kvp.Value?.ToObject()),
            _ => throw new NotSupportedException($"Unsupported DataValue type: {value.GetType().FullName}"),
        };
    }

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
