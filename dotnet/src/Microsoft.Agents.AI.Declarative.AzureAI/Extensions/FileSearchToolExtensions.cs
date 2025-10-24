// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="HostedFileSearchTool"/>.
/// </summary>
internal static class FileSearchToolExtensions
{
    /// <summary>
    /// Creates a <see cref="FileSearchToolDefinition"/> from a <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FileSearchTool"/></param>
    internal static FileSearchToolDefinition CreateFileSearchToolDefinition(this FileSearchTool tool)
    {
        Throw.IfNull(tool);

        // TODO: Add support for FileSearchToolDefinitionDetails.

        return new FileSearchToolDefinition();
    }

    /// <summary>
    /// Get the vector store IDs for the specified <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FileSearchTool"/></param>
    internal static List<string>? GetVectorStoreIds(this FileSearchTool tool)
    {
        var toolConnections = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("vectorStoreIds"));
        return toolConnections is not null
            ? [.. toolConnections.Values.Select(connection => connection.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("value"))?.Value)]
            : null;
    }

    internal static IList<VectorStoreConfigurations>? GetVectorStoreConfigurations(this FileSearchTool tool)
    {
        var dataSources = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.configurations"));
        return dataSources is not null ? dataSources.Values.Select(value => value.CreateVectorStoreConfiguration()).ToList() : null;
    }

    internal static VectorStoreConfigurations CreateVectorStoreConfiguration(this RecordDataValue value)
    {
        Throw.IfNull(value);

        var storeName = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("store_name"))?.Value;
        Throw.IfNullOrEmpty(storeName);

        var dataSources = value.GetDataSources();
        Throw.IfNull(dataSources);

        return new VectorStoreConfigurations(storeName, new VectorStoreConfiguration(dataSources));
    }
}
