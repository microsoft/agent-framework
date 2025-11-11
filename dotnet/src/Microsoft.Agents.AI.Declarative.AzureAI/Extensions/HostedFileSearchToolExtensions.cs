// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="HostedFileSearchTool"/>.
/// </summary>
internal static class HostedFileSearchToolExtensions
{
    /// <summary>
    /// Creates a <see cref="FileSearchToolDefinition"/> from a <see cref="HostedFileSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="HostedFileSearchTool"/></param>
    internal static FileSearchToolDefinition CreateFileSearchToolDefinition(this HostedFileSearchTool tool)
    {
        Throw.IfNull(tool);

        // TODO: Add support for FileSearchToolDefinitionDetails.

        return new FileSearchToolDefinition();
    }
}
