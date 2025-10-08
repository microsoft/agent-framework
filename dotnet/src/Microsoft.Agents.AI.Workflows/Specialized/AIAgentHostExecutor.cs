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

    public AIAgentHostExecutor(AIAgent agent, bool emitEvents = false) : base(id: agent.Id)
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
        emitEvents ??= this._emitEvents;
        IAsyncEnumerable<AgentRunResponseUpdate> agentStream = this._agent.RunStreamingAsync(messages, this.EnsureThread(context), cancellationToken: cancellationToken);

        List<AIContent> updates = [];
        ChatMessage? currentStreamingMessage = null;

        await foreach (AgentRunResponseUpdate update in agentStream.ConfigureAwait(false))
        {
            if (string.IsNullOrEmpty(update.MessageId))
            {
                // Ignore updates that don't have a message ID.
                continue;
            }

            if (emitEvents ?? this._emitEvents)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
            }

            // TODO: FunctionCall request handling, and user info request handling.
            // In some sense: We should just let it be handled as a ChatMessage, though we should consider
            // providing some mechanisms to help the user complete the request, or route it out of the
            // workflow.

            if (currentStreamingMessage is null || currentStreamingMessage.MessageId != update.MessageId)
            {
                await PublishCurrentMessageAsync().ConfigureAwait(false);
                currentStreamingMessage = new(update.Role ?? ChatRole.Assistant, update.Contents)
                {
                    AuthorName = update.AuthorName,
                    CreatedAt = update.CreatedAt,
                    MessageId = update.MessageId,
                    RawRepresentation = update.RawRepresentation,
                    AdditionalProperties = update.AdditionalProperties
                };
            }

            updates.AddRange(update.Contents);
        }

        await PublishCurrentMessageAsync().ConfigureAwait(false);

        async ValueTask PublishCurrentMessageAsync()
        {
            if (currentStreamingMessage is not null && updates.Count > 0)
            {
                currentStreamingMessage.Contents = updates;
                updates = [];

                await context.SendMessageAsync(currentStreamingMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            currentStreamingMessage = null;
        }
    }
}
