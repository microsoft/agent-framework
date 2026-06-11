// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class GroupChatHost(
        string id,
        AIAgent[] agents,
        Dictionary<AIAgent, ExecutorBinding> agentMap,
        Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory) : ChatProtocolExecutor(id, s_options), IResettableExecutor
{
    private static readonly ChatProtocolExecutorOptions s_options = new()
    {
        StringMessageChatRole = ChatRole.User,
        AutoSendTurnToken = false
    };

    private const string HistoryStateKey = nameof(_history);
    private const string CurrentSpeakerStateKey = nameof(_currentSpeakerExecutorId);

    private readonly AIAgent[] _agents = agents;
    private readonly Dictionary<AIAgent, ExecutorBinding> _agentMap = agentMap;
    private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory = managerFactory;

    private GroupChatManager? _manager;

    // Canonical conversation accumulated across turns. Each participant maintains its own per-agent
    // session/thread; the host keeps this only as the source of truth for the manager hooks
    // (SelectNextAgentAsync / ShouldTerminateAsync) and for the workflow's final output.
    private List<ChatMessage> _history = [];

    // Executor id of the participant we most recently dispatched a TurnToken to – i.e., the current
    // speaker whose response is about to arrive. Used to exclude that participant from the next
    // broadcast (its own session already contains the message it produced).
    private string? _currentSpeakerExecutorId;

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        => base.ConfigureProtocol(protocolBuilder).YieldsOutput<List<ChatMessage>>();

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        this._manager ??= this._managerFactory(this._agents);

        // The delta arriving here is either the initial user input (turn 0) or the most recent speaker's
        // response (subsequent turns) – participants no longer echo incoming messages back to the host.
        if (messages.Count > 0)
        {
            this._history.AddRange(messages);
        }

        if (await this._manager.ShouldTerminateAsync(this._history, cancellationToken).ConfigureAwait(false))
        {
            await this.CompleteAsync(context, cancellationToken).ConfigureAwait(false);
            return;
        }

        if (messages.Count > 0)
        {
            IEnumerable<ChatMessage> filteredDelta = await this._manager.UpdateHistoryAsync(messages, cancellationToken).ConfigureAwait(false);
            List<ChatMessage> broadcastMessages = filteredDelta is null
                ? messages
                : (ReferenceEquals(filteredDelta, messages) ? messages : [.. filteredDelta]);

            if (broadcastMessages.Count > 0)
            {
                await this.BroadcastAsync(broadcastMessages, context, cancellationToken).ConfigureAwait(false);
            }
        }

        if (await this._manager.SelectNextAgentAsync(this._history, cancellationToken).ConfigureAwait(false) is AIAgent nextAgent &&
            this._agentMap.TryGetValue(nextAgent, out ExecutorBinding? executor))
        {
            this._manager.IterationCount++;
            this._currentSpeakerExecutorId = executor.Id;
            await context.SendMessageAsync(new TurnToken(emitEvents), executor.Id, cancellationToken).ConfigureAwait(false);
            return;
        }

        await this.CompleteAsync(context, cancellationToken).ConfigureAwait(false);
    }

    private ValueTask BroadcastAsync(List<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
    {
        List<Task>? sendTasks = null;
        foreach (ExecutorBinding participant in this._agentMap.Values)
        {
            if (string.Equals(participant.Id, this._currentSpeakerExecutorId, StringComparison.Ordinal))
            {
                continue;
            }

            (sendTasks ??= []).Add(context.SendMessageAsync(messages, participant.Id, cancellationToken).AsTask());
        }

        return sendTasks is null ? default : new ValueTask(Task.WhenAll(sendTasks));
    }

    private async ValueTask CompleteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage> output = this._history;
        this._history = [];
        this._currentSpeakerExecutorId = null;
        this._manager = null;

        await context.YieldOutputAsync(output, cancellationToken).ConfigureAwait(false);
    }

    protected override ValueTask ResetAsync()
    {
        this._manager = null;
        this._history = [];
        this._currentSpeakerExecutorId = null;

        return base.ResetAsync();
    }

    ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task historyTask = context.QueueStateUpdateAsync(HistoryStateKey, this._history, cancellationToken: cancellationToken).AsTask();
        Task currentSpeakerTask = context.QueueStateUpdateAsync(CurrentSpeakerStateKey, this._currentSpeakerExecutorId, cancellationToken: cancellationToken).AsTask();
        Task baseTask = base.OnCheckpointingAsync(context, cancellationToken).AsTask();

        // Eagerly materialize the manager so subclass state (e.g., the round-robin cursor) gets
        // persisted on every checkpoint, even if no turn has been taken yet since the host was constructed.
        this._manager ??= this._managerFactory(this._agents);
        Task managerTask = this._manager.CheckpointAsync(context, cancellationToken).AsTask();

        await Task.WhenAll(historyTask, currentSpeakerTask, baseTask, managerTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._history = await context.ReadStateAsync<List<ChatMessage>>(HistoryStateKey, cancellationToken: cancellationToken).ConfigureAwait(false) ?? [];
        this._currentSpeakerExecutorId = await context.ReadStateAsync<string?>(CurrentSpeakerStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);

        // Instantiate the manager eagerly so its restore hook can rehydrate IterationCount and any
        // subclass-defined state (e.g., RoundRobinGroupChatManager._nextIndex).
        this._manager = this._managerFactory(this._agents);
        await this._manager.RestoreCheckpointAsync(context, cancellationToken).ConfigureAwait(false);

        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);
    }
}
