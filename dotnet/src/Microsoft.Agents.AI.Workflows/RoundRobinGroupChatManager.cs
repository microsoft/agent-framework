// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a <see cref="GroupChatManager"/> that selects agents in a round-robin fashion.
/// </summary>
public class RoundRobinGroupChatManager : GroupChatManager
{
    private readonly IReadOnlyList<AIAgent> _agents;
    private readonly Func<RoundRobinGroupChatManager, IEnumerable<ChatMessage>, CancellationToken, ValueTask<bool>>? _shouldTerminateFunc;
    private int _nextIndex;

    /// <summary>
    /// Initializes a new instance of the <see cref="RoundRobinGroupChatManager"/> class.
    /// </summary>
    /// <param name="agents">The agents to be managed as part of this workflow.</param>
    /// <param name="shouldTerminateFunc">
    /// An optional function that determines whether the group chat should terminate based on the chat history
    /// before factoring in the default behavior, which is to terminate based only on the iteration count.
    /// </param>
    public RoundRobinGroupChatManager(
        IReadOnlyList<AIAgent> agents,
        Func<RoundRobinGroupChatManager, IEnumerable<ChatMessage>, CancellationToken, ValueTask<bool>>? shouldTerminateFunc = null)
    {
        Throw.IfNullOrEmpty(agents);
        foreach (var agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
        }

        this._agents = agents;
        this._shouldTerminateFunc = shouldTerminateFunc;
    }

    /// <inheritdoc />
    protected internal override ValueTask<AIAgent> SelectNextAgentAsync(
        IReadOnlyList<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        AIAgent nextAgent = this._agents[this._nextIndex];

        this._nextIndex = (this._nextIndex + 1) % this._agents.Count;

        return new ValueTask<AIAgent>(nextAgent);
    }

    /// <inheritdoc />
    protected internal override async ValueTask<bool> ShouldTerminateAsync(
        IReadOnlyList<ChatMessage> history, CancellationToken cancellationToken = default)
    {
        if (this._shouldTerminateFunc is { } func && await func(this, history, cancellationToken).ConfigureAwait(false))
        {
            return true;
        }

        return await base.ShouldTerminateAsync(history, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    protected internal override void Reset()
    {
        base.Reset();
        this._nextIndex = 0;
    }

    /// <inheritdoc />
    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        => context.QueueStateUpdateAsync(StateKey, new RoundRobinGroupChatManagerState(this._nextIndex), cancellationToken: cancellationToken);

    /// <inheritdoc />
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        RoundRobinGroupChatManagerState? state = await context.ReadStateAsync<RoundRobinGroupChatManagerState>(StateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        this._nextIndex = state?.NextIndex ?? 0;
        if (this._nextIndex < 0 || this._nextIndex >= this._agents.Count)
        {
            this._nextIndex = 0;
        }
    }

    private const string StateKey = "next_index";
}

internal sealed record RoundRobinGroupChatManagerState(int NextIndex);
