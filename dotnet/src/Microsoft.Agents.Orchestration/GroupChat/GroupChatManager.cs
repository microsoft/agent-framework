// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Represents the result of a group chat manager operation, including a value and a reason.
/// </summary>
/// <typeparam name="TValue">The type of the value returned by the operation.</typeparam>
/// <param name="value">The value returned by the operation.</param>
public sealed class GroupChatManagerResult<TValue>(TValue value)
{
    /// <summary>
    /// The reason for the result, providing additional context or explanation.
    /// </summary>
    public string Reason { get; init; } = string.Empty;

    /// <summary>
    /// The value returned by the group chat manager operation.
    /// </summary>
    public TValue Value { get; } = value;
}

/// <summary>
/// A manager that manages the flow of a group chat.
/// </summary>
public abstract class GroupChatManager
{
    private int _invocationCount;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatManager"/> class.
    /// </summary>
    protected GroupChatManager() { }

    /// <summary>
    /// Gets the number of times the group chat manager has been invoked.
    /// </summary>
    public int InvocationCount => this._invocationCount;

    /// <summary>
    /// Gets or sets the maximum number of invocations allowed for the group chat manager.
    /// </summary>
    public int MaximumInvocationCount { get; init; } = int.MaxValue;

    /// <summary>
    /// Gets or sets the callback to be invoked for interactive input.
    /// </summary>
    public Func<ValueTask<ChatMessage>>? InteractiveCallback { get; init; }

    /// <summary>
    /// Filters the results of the group chat based on the provided chat history.
    /// </summary>
    /// <param name="history">The chat history to filter.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A <see cref="GroupChatManagerResult{TValue}"/> containing the filtered result as a string.</returns>
    protected internal abstract ValueTask<GroupChatManagerResult<string>> FilterResultsAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default);

    /// <summary>
    /// Selects the next agent to participate in the group chat based on the provided chat history and team.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="team">The group of agents participating in the chat.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A <see cref="GroupChatManagerResult{TValue}"/> containing the identifier of the next agent as a string.</returns>
    protected internal abstract ValueTask<GroupChatManagerResult<string>> SelectNextAgentAsync(IReadOnlyCollection<ChatMessage> history, GroupChatTeam team, CancellationToken cancellationToken = default);

    /// <summary>
    /// Determines whether user input should be requested based on the provided chat history.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A <see cref="GroupChatManagerResult{TValue}"/> indicating whether user input should be requested.</returns>
    protected internal abstract ValueTask<GroupChatManagerResult<bool>> ShouldRequestUserInputAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default);

    /// <summary>
    /// Determines whether the group chat should be terminated based on the provided chat history and invocation count.
    /// </summary>
    /// <param name="history">The chat history to consider.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A <see cref="GroupChatManagerResult{TValue}"/> indicating whether the chat should be terminated.</returns>
    protected internal virtual ValueTask<GroupChatManagerResult<bool>> ShouldTerminateAsync(IReadOnlyCollection<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        bool resultValue = false;
        string reason = "Maximum number of invocations has not been reached.";
        if (Interlocked.Increment(ref this._invocationCount) > this.MaximumInvocationCount)
        {
            resultValue = true;
            reason = "Maximum number of invocations reached.";
        }

        GroupChatManagerResult<bool> result = new(resultValue) { Reason = reason };
        return new ValueTask<GroupChatManagerResult<bool>>(result);
    }
}
