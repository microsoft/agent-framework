// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Specialized;

internal sealed class AIAgentHostExecutor : Executor
{
    private readonly bool _emitEvents;
    private readonly AIAgent _agent;
    private readonly List<ChatMessage> _pendingMessages = [];
    private AgentThread? _thread;

    public AIAgentHostExecutor(AIAgent agent, bool emitEvents = false) : base(id: agent.Id)
    {
        this._agent = agent;
        this._emitEvents = emitEvents;
    }

    private AgentThread EnsureThread(IWorkflowContext context) =>
        this._thread ??= this._agent.GetNewThread();

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<ChatMessage>(this.QueueMessageAsync)
                    .AddHandler<List<ChatMessage>>(this.QueueMessagesAsync)
                    .AddHandler<TurnToken>(this.TakeTurnAsync);

    public ValueTask QueueMessagesAsync(List<ChatMessage> messages, IWorkflowContext context)
    {
        this._pendingMessages.AddRange(messages);
        return default;
    }

    public ValueTask QueueMessageAsync(ChatMessage message, IWorkflowContext context)
    {
        this._pendingMessages.Add(message);
        return default;
    }

    private const string ThreadStateKey = nameof(_thread);
    private const string PendingMessagesStateKey = nameof(_pendingMessages);
    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        Task threadTask = Task.CompletedTask;
        if (this._thread is not null)
        {
            JsonElement threadValue = await this._thread.SerializeAsync(cancellationToken: cancellation).ConfigureAwait(false);
            threadTask = context.QueueStateUpdateAsync(ThreadStateKey, threadValue).AsTask();
        }

        Task messagesTask = Task.CompletedTask;
        if (this._pendingMessages.Count > 0)
        {
            JsonElement messagesValue = this._pendingMessages.SerializeToJson();
            messagesTask = context.QueueStateUpdateAsync(PendingMessagesStateKey, messagesValue).AsTask();
        }

        await Task.WhenAll(threadTask, messagesTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        JsonElement? threadValue = await context.ReadStateAsync<JsonElement?>(ThreadStateKey).ConfigureAwait(false);
        if (threadValue.HasValue)
        {
            this._thread = this._agent.DeserializeThread(threadValue.Value, cancellationToken: cancellation);
        }

        JsonElement? messagesValue = await context.ReadStateAsync<JsonElement?>(PendingMessagesStateKey).ConfigureAwait(false);
        if (messagesValue.HasValue)
        {
            List<ChatMessage> messages = messagesValue.Value.DeserializeMessageList();
            this._pendingMessages.AddRange(messages);
        }
    }

    public async ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context)
    {
        bool emitEvents = token.EmitEvents ?? this._emitEvents;
        IAsyncEnumerable<AgentRunResponseUpdate> agentStream = this._agent.RunStreamingAsync(this._pendingMessages, this.EnsureThread(context));

        List<AIContent> updates = [];
        ChatMessage? currentStreamingMessage = null;

        await foreach (AgentRunResponseUpdate update in agentStream.ConfigureAwait(false))
        {
            if (string.IsNullOrEmpty(update.MessageId))
            {
                // Ignore updates that don't have a message ID.
                continue;
            }

            if (emitEvents)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
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
        await context.SendMessageAsync(token).ConfigureAwait(false);

        async ValueTask PublishCurrentMessageAsync()
        {
            if (currentStreamingMessage is not null)
            {
                currentStreamingMessage.Contents = updates;
                updates = [];

                await context.SendMessageAsync(currentStreamingMessage).ConfigureAwait(false);
            }

            currentStreamingMessage = null;
        }
    }
}
