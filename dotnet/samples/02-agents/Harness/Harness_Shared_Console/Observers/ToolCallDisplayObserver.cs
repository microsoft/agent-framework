// Copyright (c) Microsoft. All rights reserved.

using Harness.Shared.Console.ToolFormatters;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays tool call notifications (🔧) for <see cref="FunctionCallContent"/>
/// and <see cref="ToolCallContent"/> items in the response stream.
/// </summary>
public sealed class ToolCallDisplayObserver : ConsoleObserver
{
    private readonly IReadOnlyList<ToolCallFormatter> _formatters;

    /// <summary>
    /// Initializes a new instance of the <see cref="ToolCallDisplayObserver"/> class.
    /// </summary>
    /// <param name="formatters">Optional list of tool formatters. When <see langword="null"/>,
    /// the default formatters from <see cref="ToolCallFormatter.BuildDefaultToolFormatters"/> are used.</param>
    public ToolCallDisplayObserver(IReadOnlyList<ToolCallFormatter>? formatters = null)
    {
        this._formatters = formatters ?? ToolCallFormatter.BuildDefaultToolFormatters();
    }

    /// <inheritdoc/>
    public override async Task OnContentAsync(IUXStateDriver ux, AIContent content, AIAgent agent, AgentSession session)
    {
        if (content is FunctionCallContent functionCall)
        {
            await ux.WriteInfoLineAsync($"🔧 Calling tool: {ToolCallFormatter.Format(this._formatters, functionCall)}...", ConsoleColor.DarkYellow);
        }
        else if (content is WebSearchToolCallContent)
        {
            // Handled by OpenAIResponsesWebSearchDisplayObserver when present; skip here to avoid duplication.
        }
        else if (content is ToolCallContent toolCall)
        {
            await ux.WriteInfoLineAsync($"🔧 Calling tool: {toolCall}...", ConsoleColor.DarkYellow);
        }
    }
}
