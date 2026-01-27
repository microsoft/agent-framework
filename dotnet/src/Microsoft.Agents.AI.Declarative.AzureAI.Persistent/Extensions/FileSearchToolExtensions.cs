// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="FileSearchTool"/>.
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
    /// Creates an <see cref="OpenAI.Responses.FileSearchTool"/> from a <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FileSearchTool"/></param>
    /// <returns>A new <see cref="OpenAI.Responses.FileSearchTool"/> instance configured with the vector store IDs.</returns>
    internal static OpenAI.Responses.FileSearchTool CreateFileSearchTool(this FileSearchTool tool)
    {
        Throw.IfNull(tool);

        return new OpenAI.Responses.FileSearchTool(tool.GetVectorStoreIds());
    }

    /// <summary>
    /// Get the vector store IDs for the specified <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FileSearchTool"/></param>
    internal static List<string>? GetVectorStoreIds(this FileSearchTool tool)
    {
        return tool.VectorStoreIds?.LiteralValue.ToList();
    }

    internal static IList<VectorStoreConfigurations>? GetVectorStoreConfigurations(this FileSearchTool tool)
    {
        var dataSources = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.configurations"));
        return dataSources?.Values.Select(value => value.CreateVectorStoreConfiguration()).ToList();
    }

    internal static VectorStoreConfigurations CreateVectorStoreConfiguration(this RecordDataValue value)
    {
        Throw.IfNull(value);

        var storeName = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("storeName"))?.Value;
        Throw.IfNullOrEmpty(storeName);

        var dataSources = value.GetDataSources();
        Throw.IfNull(dataSources);

        return new VectorStoreConfigurations(storeName, new VectorStoreConfiguration(dataSources));
    }
}
