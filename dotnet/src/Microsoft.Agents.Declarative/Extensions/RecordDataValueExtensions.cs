// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataValue"/> and <see cref="RecordDataValue"/>.
/// </summary>
public static class RecordDataValueExtensions
{
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
}
