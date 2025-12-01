// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataType"/>.
/// </summary>
public static class RecordDataTypeExtensions
{
    /// <summary>
    /// Creates a <see cref="ChatResponseFormat"/> from a <see cref="RecordDataType"/>.
    /// </summary>
    /// <param name="recordDataType">Instance of <see cref="RecordDataType"/></param>
    internal static ChatResponseFormat? AsChatResponseFormat(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        if (recordDataType.Properties.Count == 0)
        {
            return null;
        }

        // TODO: Consider adding schemaName and schemaDescription parameters to this method.
        return ChatResponseFormat.ForJsonSchema(
            schema: recordDataType.GetSchema(),
            schemaName: recordDataType.GetSchemaName(),
            schemaDescription: recordDataType.GetSchemaDescription());
    }

    /// <summary>
    /// Converts a <see cref="RecordDataType"/> to a <see cref="JsonElement"/>.
    /// </summary>
    /// <param name="recordDataType">Instance of <see cref="RecordDataType"/></param>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    public static JsonElement GetSchema(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        var schemaObject = new Dictionary<string, object>
        {
            ["type"] = "object",
            ["properties"] = recordDataType.Properties.AsObjectDictionary(),
            ["additionalProperties"] = false
        };

        var json = JsonSerializer.Serialize(schemaObject, ElementSerializer.CreateOptions());
        return JsonSerializer.Deserialize<JsonElement>(json);
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

    /// <summary>
    /// Retrieves the 'schemaName' property from a <see cref="RecordDataType"/>.
    /// </summary>
    private static string? GetSchemaName(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        return recordDataType.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schemaName"))?.Value;
    }

    /// <summary>
    /// Retrieves the 'schemaDescription' property from a <see cref="RecordDataType"/>.
    /// </summary>
    private static string? GetSchemaDescription(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        return recordDataType.ExtensionData?.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("schemaDescription"))?.Value;
    }
}
