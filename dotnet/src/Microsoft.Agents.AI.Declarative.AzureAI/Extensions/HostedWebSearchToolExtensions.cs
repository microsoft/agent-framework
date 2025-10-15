// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="HostedWebSearchTool"/>.
/// </summary>
internal static class HostedWebSearchToolExtensions
{
    /// <summary>
    /// Creates a <see cref="BingGroundingToolDefinition"/> from a <see cref="HostedWebSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="HostedWebSearchTool"/></param>
    internal static BingGroundingToolDefinition CreateBingGroundingToolDefinition(this HostedWebSearchTool tool)
    {
        Throw.IfNull(tool);

        // TODO: Add support for BingGroundingSearchToolParameters.
        var parameters = new BingGroundingSearchToolParameters([]);

        return new BingGroundingToolDefinition(parameters);
    }
}
