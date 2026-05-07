// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.Observers;

/// <summary>
/// Displays tool call notifications (🔧) for <see cref="FunctionCallContent"/>
/// and <see cref="ToolCallContent"/> items in the response stream.
/// </summary>
internal sealed class ToolCallDisplayObserver : ConsoleObserver
{
    /// <inheritdoc/>
    public override async Task OnContentAsync(ConsoleWriter writer, AIContent content)
    {
        if (content is FunctionCallContent functionCall)
        {
            await writer.WriteInfoLineAsync($"🔧 Calling tool: {ToolCallFormatter.Format(functionCall)}...", ConsoleColor.DarkYellow);
        }
        else if (content is ToolCallContent toolCall)
        {
            await writer.WriteInfoLineAsync($"🔧 Calling tool: {toolCall}...", ConsoleColor.DarkYellow);
        }
    }
}
