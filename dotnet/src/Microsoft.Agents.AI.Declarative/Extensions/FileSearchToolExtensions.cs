// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="FileSearchTool"/>.
/// </summary>
public static class FileSearchToolExtensions
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
            Inputs = tool.Inputs.Select(input =>
            {
                return input switch
                {
                    VectorStoreContent => (Microsoft.Extensions.AI.AIContent)new HostedVectorStoreContent(((VectorStoreContent)input).VectorStoreId!),
                    _ => throw new NotSupportedException($"Unable to create file search input because of unsupported input type: {input.Kind}"),
                };
            }).ToList(),
        };
    }
}
