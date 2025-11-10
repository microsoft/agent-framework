// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="FileSearchTool"/>.
/// </summary>
internal static class FileSearchToolExtensions
{
    /// <summary>
    /// Create a <see cref="HostedFileSearchTool"/> from a <see cref="FileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FileSearchTool"/></param>
    internal static HostedFileSearchTool CreateFileSearchTool(this FileSearchTool tool)
    {
        Throw.IfNull(tool);

        return new HostedFileSearchTool()
        {
            MaximumResultCount = (int?)tool.MaximumResultCount?.LiteralValue,
            Inputs = tool.VectorStoreIds?.LiteralValue.Select(id => (AIContent)new HostedVectorStoreContent(id)).ToList(),
        };
    }
}
