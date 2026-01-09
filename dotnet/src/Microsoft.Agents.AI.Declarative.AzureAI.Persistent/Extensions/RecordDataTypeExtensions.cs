// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataType"/>.
/// </summary>
internal static class RecordDataTypeExtensions
{
    /// <summary>
    /// Creates a <see cref="ChatResponseFormat"/> from a <see cref="RecordDataType"/>.
    /// </summary>
    /// <param name="recordDataType">Instance of <see cref="RecordDataType"/></param>
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
    internal static BinaryData? AsBinaryData(this RecordDataType recordDataType)
    {
        Throw.IfNull(recordDataType);

        if (recordDataType.Properties.Count == 0)
        {
            return null;
        }

        return BinaryData.FromObjectAsJson(
            new
            {
                type = "json_schema",
                schema =
                new
                {
                    type = "object",
                    properties = recordDataType.Properties.AsObjectDictionary(),
                    additionalProperties = false
                }
            }
        );
    }
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
}
