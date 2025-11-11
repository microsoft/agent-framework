// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="RecordDataValue"/>.
/// </summary>
internal static class RecordDataValueExtensions
{
    /// <summary>
    /// Gets the data sources from the specified <see cref="RecordDataValue"/>.
    /// </summary>
    internal static List<VectorStoreDataSource>? GetDataSources(this RecordDataValue value)
    {
        var dataSources = value.GetPropertyOrNull<TableDataValue>(InitializablePropertyPath.Create("options.data_sources"));
        return dataSources?.Values.Select(dataSource => dataSource.CreateDataSource()).ToList();
    }

    /// <summary>
    /// Creates a new instance of <see cref="VectorStoreDataSource"/> using the specified <see cref="RecordDataValue"/>.
    /// </summary>
    internal static VectorStoreDataSource CreateDataSource(this RecordDataValue value)
    {
        Throw.IfNull(value);

        string? assetIdentifier = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("assetIdentifier"))?.Value;
        Throw.IfNullOrEmpty(assetIdentifier);

        string? assetType = value.GetPropertyOrNull<StringDataValue>(InitializablePropertyPath.Create("assetType"))?.Value;
        Throw.IfNullOrEmpty(assetType);

        return new VectorStoreDataSource(assetIdentifier, new VectorStoreDataSourceAssetType(assetType));
    }
}
