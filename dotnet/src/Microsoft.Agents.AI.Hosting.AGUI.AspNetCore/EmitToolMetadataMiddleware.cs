// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// This middleware enriches tool result content with tool metadata.
/// </summary>
public static class EmitToolMetadataMiddleware
{
    /// <summary>
    /// Enriches tool result contents with tool metadata (e.g. MCP Tool Meta).
    /// </summary>
    public static AIAgentBuilder UseEmitToolMetadata(this AIAgentBuilder agentBuilder, Dictionary<string, JsonObject?> metadata)
    {
        ArgumentNullException.ThrowIfNull(metadata);
        return agentBuilder.Use(async (agent, context, next, cancel) =>
        {
            var result = await next(context, cancel).ConfigureAwait(false);
            if (result is AIContent content)
            {
                var toolMetadata = metadata.TryGetValue(context.Function.Name, out var meta) ? meta : null;
                if (toolMetadata is not null)
                {
                    content.AdditionalProperties ??= [];
                    if (!content.AdditionalProperties.ContainsKey("ToolMetadata"))
                    {
                        content.AdditionalProperties["ToolMetadata"] = toolMetadata;
                    }
                    else
                    {
                        throw new InvalidOperationException($"Result content of tool '{context.Function.Name}' already contains 'ToolMetadata' in AdditionalProperties.");
                    }
                }
            }
            return result;
        });
    }
}
