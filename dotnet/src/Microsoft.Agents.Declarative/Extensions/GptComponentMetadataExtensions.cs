// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
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
    /// Retrieves the 'tools' property from a <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="element">Instance of <see cref="GptComponentMetadata"/></param>
    public static string? GetInstructions(this GptComponentMetadata element)
    {
        Throw.IfNull(element);

        return element.Instructions?.ToTemplateString();
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
}
