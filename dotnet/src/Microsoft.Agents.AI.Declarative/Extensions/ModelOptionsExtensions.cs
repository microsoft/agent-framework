// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="ModelOptions"/>.
/// </summary>
internal static class ModelOptionsExtensions
{
    /// <summary>
    /// Converts the 'chatToolMode' property from a <see cref="ModelOptions"/> to a <see cref="ChatToolMode"/>.
    /// </summary>
    /// <param name="modelOptions">Instance of <see cref="ModelOptions"/></param>
    internal static ChatToolMode? AsChatToolMode(this ModelOptions modelOptions)
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
    internal static AdditionalPropertiesDictionary? GetAdditionalProperties(this ModelOptions modelOptions, string[] excludedProperties)
    {
        Throw.IfNull(modelOptions);

        var options = modelOptions.ExtensionData;
        if (options is null || options.Properties.Count == 0)
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
