// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="CodeInterpreterTool"/>.
/// </summary>
internal static class CodeInterpreterToolExtensions
{
    /// <summary>
    /// Creates a <see cref="CodeInterpreterToolDefinition"/> from a <see cref="CodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static CodeInterpreterToolDefinition CreateCodeInterpreterToolDefinition(this CodeInterpreterTool tool)
    {
        Throw.IfNull(tool);

        return new CodeInterpreterToolDefinition();
    }

    /// <summary>
    /// Collects the file IDs from the extension data of a <see cref="CodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static List<string>? GetFileIds(this CodeInterpreterTool tool)
    {
        var fileIds = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("fileIds"));
        return fileIds is not null
            ? [.. fileIds.Values.Select(fileId => fileId.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("value"))?.Value)]
            : null;
    }

    /// <summary>
    /// Collects the data sources from the extension data of a <see cref="CodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static List<VectorStoreDataSource>? GetDataSources(this CodeInterpreterTool tool)
    {
        var dataSources = tool.ExtensionData?.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("dataSources"));
        return dataSources is not null
            ? dataSources.Values.Select(dataSource => dataSource.CreateDataSource()).ToList()
            : null;
    }
}
