// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class AIAgentHostExecutor : ChatProtocolExecutor
{
    private readonly bool _emitEvents;
    private readonly AIAgent _agent;
    private AgentThread? _thread;

    public AIAgentHostExecutor(AIAgent agent, bool emitEvents = false) : base(id: agent.GetDescriptiveId())
    {
        this._agent = agent;
        this._emitEvents = emitEvents;
    }

    private AgentThread EnsureThread(IWorkflowContext context) =>
        this._thread ??= this._agent.GetNewThread();

    private const string ThreadStateKey = nameof(_thread);
    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task threadTask = Task.CompletedTask;
        if (this._thread is not null)
        {
            JsonElement threadValue = this._thread.Serialize();
            threadTask = context.QueueStateUpdateAsync(ThreadStateKey, threadValue, cancellationToken: cancellationToken).AsTask();
        }

        Task baseTask = base.OnCheckpointingAsync(context, cancellationToken).AsTask();

        await Task.WhenAll(threadTask, baseTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        JsonElement? threadValue = await context.ReadStateAsync<JsonElement?>(ThreadStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (threadValue.HasValue)
        {
            this._thread = this._agent.DeserializeThread(threadValue.Value);
        }

        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);
    }

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        if (emitEvents ?? this._emitEvents)
        {
            // Run the agent in streaming mode only when agent run update events are to be emitted.
            IAsyncEnumerable<AgentRunResponseUpdate> agentStream = this._agent.RunStreamingAsync(messages, this.EnsureThread(context), cancellationToken: cancellationToken);

            List<AgentRunResponseUpdate> updates = [];

            await foreach (AgentRunResponseUpdate update in agentStream.ConfigureAwait(false))
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);

                // TODO: FunctionCall request handling, and user info request handling.
                // In some sense: We should just let it be handled as a ChatMessage, though we should consider
                // providing some mechanisms to help the user complete the request, or route it out of the
                // workflow.
                updates.Add(update);
            }

            await context.SendMessageAsync(updates.ToAgentRunResponse().Messages, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        else
        {
            // Otherwise, run the agent in non-streaming mode.
            AgentRunResponse response = await this._agent.RunAsync(messages, this.EnsureThread(context), cancellationToken: cancellationToken).ConfigureAwait(false);
            await context.SendMessageAsync(response.Messages, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
    }
}
