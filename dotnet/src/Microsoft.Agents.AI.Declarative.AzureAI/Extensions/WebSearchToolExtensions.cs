// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="WebSearchTool"/>.
/// </summary>
internal static class WebSearchToolExtensions
{
    /// <summary>
    /// Creates a <see cref="BingGroundingToolDefinition"/> from a <see cref="WebSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="WebSearchTool"/></param>
    internal static BingGroundingToolDefinition CreateBingGroundingToolDefinition(this WebSearchTool tool)
    {
        Throw.IfNull(tool);

        // TODO: Add support for BingGroundingSearchToolParameters.
        var parameters = new BingGroundingSearchToolParameters([]);

        return new BingGroundingToolDefinition(parameters);
    }
}
