// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="WebSearchTool"/>.
/// </summary>
internal static class WebSearchToolExtensions
{
    /// <summary>
    /// Create a <see cref="HostedWebSearchTool"/> from a <see cref="WebSearchTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="WebSearchTool"/></param>
    internal static HostedWebSearchTool CreateWebSearchTool(this WebSearchTool tool)
    {
        Throw.IfNull(tool);

        return new HostedWebSearchTool();
    }
}
