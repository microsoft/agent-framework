// Copyright (c) Microsoft. All rights reserved.

using System;
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
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    public static BinaryData? AsBinaryData(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        var schemaObject = new Dictionary<string, object>
        {
            ["type"] = "object",
            ["properties"] = recordDataType.Properties.AsObjectDictionary(),
            ["additionalProperties"] = false
        };

        var json = JsonSerializer.Serialize(schemaObject, ElementSerializer.CreateOptions());
        return new BinaryData(json);
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
}
