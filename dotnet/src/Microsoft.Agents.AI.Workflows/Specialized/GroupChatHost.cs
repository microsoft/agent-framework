// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class GroupChatHost(
        string id,
        AIAgent[] agents,
        Dictionary<AIAgent, ExecutorIsh> agentMap,
        Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory) : Executor(id), IResettableExecutor
{
    private readonly AIAgent[] _agents = agents;
    private readonly Dictionary<AIAgent, ExecutorIsh> _agentMap = agentMap;
    private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory = managerFactory;
    private readonly List<ChatMessage> _pendingMessages = [];

    private GroupChatManager? _manager;

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) => routeBuilder
        .AddHandler<string>((message, context, _) => this._pendingMessages.Add(new(ChatRole.User, message)))
        .AddHandler<ChatMessage>((message, context, _) => this._pendingMessages.Add(message))
        .AddHandler<IEnumerable<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))
        .AddHandler<ChatMessage[]>((messages, _, __) => this._pendingMessages.AddRange(messages)) // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
        .AddHandler<List<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))  // TODO: Remove once https://github.com/microsoft/agent-framework/issues/782 is addressed
        .AddHandler<TurnToken>(async (token, context, cancellationToken) =>
        {
            List<ChatMessage> messages = [.. this._pendingMessages];
            this._pendingMessages.Clear();

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
                    await context.SendMessageAsync(token, executor.Id, cancellationToken).ConfigureAwait(false);
                    return;
                }
            }

            this._manager = null;
            await context.YieldOutputAsync(messages, cancellationToken).ConfigureAwait(false);
        });

    public ValueTask ResetAsync()
    {
        this._pendingMessages.Clear();
        this._manager = null;

        return default;
    }
}
