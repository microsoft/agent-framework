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

    private readonly AIAgent[] _agents = agents;
    private readonly Dictionary<AIAgent, ExecutorBinding> _agentMap = agentMap;
    private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory = managerFactory;

    private GroupChatManager? _manager;

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        => base.ConfigureProtocol(protocolBuilder).YieldsOutput<List<ChatMessage>>();

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        this._manager ??= this._managerFactory(this._agents);

        if (!await this._manager.ShouldTerminateAsync(messages, cancellationToken).ConfigureAwait(false))
        {
            var filtered = await this._manager.UpdateHistoryAsync(messages, cancellationToken).ConfigureAwait(false);
            messages = filtered is null || ReferenceEquals(filtered, messages) ? messages : [.. filtered];

            if (await this._manager.SelectNextAgentAsync(messages, cancellationToken).ConfigureAwait(false) is AIAgent nextAgent &&
                this._agentMap.TryGetValue(nextAgent, out var executor))
            {
                this._manager.IterationCount++;
                await context.SendMessageAsync(messages, executor.Id, cancellationToken).ConfigureAwait(false);
                await context.SendMessageAsync(new TurnToken(emitEvents), executor.Id, cancellationToken).ConfigureAwait(false);
                return;
            }
        }

        this._manager = null;
        await context.YieldOutputAsync(messages, cancellationToken).ConfigureAwait(false);
    }
    protected override ValueTask ResetAsync()
    {
        this._manager = null;

        return base.ResetAsync();
    }

    ValueTask IResettableExecutor.ResetAsync() => this.ResetAsync();
}
