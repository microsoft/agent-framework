// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A manager that manages the flow of a group chat.
/// </summary>
public abstract class GroupChatManager
{
    private int _maximumIterationCount = 40;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatManager"/> class.
    /// </summary>
    protected GroupChatManager() { }

    /// <summary>
    /// Gets the number of iterations in the group chat so far.
    /// </summary>
    public int IterationCount { get; internal set; }

    /// <summary>
    /// Gets or sets the maximum number of iterations allowed.
    /// </summary>
    /// <remarks>
    /// Each iteration involves a single interaction with a participating agent.
    /// The default is 40.
    /// </remarks>
    public int MaximumIterationCount
    {
        get => this._maximumIterationCount;
        set => this._maximumIterationCount = Throw.IfLessThan(value, 1);
    }

    /// <summary>
    /// Selects the next agent to participate in the group chat based on the provided chat history and team.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The next <see cref="AIAgent"/> to speak. This agent must be part of the chat.</returns>
    protected internal abstract ValueTask<AIAgent> SelectNextAgentAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Filters the chat history before it's passed to the next agent.
    /// </summary>
    /// <param name="history">The chat history to filter.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The filtered chat history.</returns>
    protected internal virtual ValueTask<IEnumerable<ChatMessage>> UpdateHistoryAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default) =>
        new(history);

    /// <summary>
    /// Determines whether the group chat should be terminated based on the provided chat history and iteration count.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="bool"/> indicating whether the chat should be terminated.</returns>
    protected internal virtual ValueTask<bool> ShouldTerminateAsync(
        IReadOnlyList<ChatMessage> history,
        CancellationToken cancellationToken = default) =>
        new(this.MaximumIterationCount is int max && this.IterationCount >= max);

    /// <summary>
    /// Resets the state of the manager for a new group chat session.
    /// </summary>
    protected internal virtual void Reset()
    {
        this.IterationCount = 0;
    }
}
