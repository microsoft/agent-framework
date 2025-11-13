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

    /// <summary>
    /// Creates a <see cref="OpenAI.Responses.WebSearchTool"/> from a <see cref="WebSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="WebSearchTool"/></param>
    /// <returns>A new <see cref="OpenAI.Responses.WebSearchTool"/> instance.</returns>
    internal static OpenAI.Responses.WebSearchTool CreateWebSearchTool(this WebSearchTool tool)
    {
        Throw.IfNull(tool);

        return new OpenAI.Responses.WebSearchTool();
    }
}
