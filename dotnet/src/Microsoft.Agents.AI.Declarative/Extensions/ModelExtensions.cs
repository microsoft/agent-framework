// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="Model"/>.
/// </summary>
public static class ModelExtensions
{
    /// <summary>
    /// Retrieves the 'apiType' property from a <see cref="Model"/>.
    /// </summary>
    /// <param name="model">Instance of <see cref="Model"/></param>
    public static string? GetApiType(this Model model)
    {
        Throw.IfNull(model);

        try
        {
            var typeValue = model.ExtensionData?.GetProperty<StringDataValue>(InitializablePropertyPath.Create("apiType"));
            return typeValue?.Value;
        }
        catch (Exception)
        {
            return null;
        }
    }
}
