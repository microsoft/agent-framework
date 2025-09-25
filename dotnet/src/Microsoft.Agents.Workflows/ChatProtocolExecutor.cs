// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows;

internal class ChatProtocolExecutorOptions
{
    public ChatRole? StringMessageChatRole { get; set; }
}

internal abstract class ChatProtocolExecutor(string id, ChatProtocolExecutorOptions? options = null) : Executor(id)
{
    private List<ChatMessage> _pendingMessages = [];
    private readonly ChatRole? _stringMessageChatRole = options?.StringMessageChatRole;

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        if (this._stringMessageChatRole.HasValue)
        {
            routeBuilder = routeBuilder.AddHandler<string>((message, _) => this._pendingMessages.Add(new(this._stringMessageChatRole.Value, message)));
        }

        return routeBuilder.AddHandler<ChatMessage>((message, _) => this._pendingMessages.Add(message))
                           .AddHandler<List<ChatMessage>>((messages, _) => this._pendingMessages.AddRange(messages))
                           .AddHandler<TurnToken>(this.TakeTurnAsync);
    }

    public async ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context)
    {
        await this.TakeTurnAsync(this._pendingMessages, context, token.EmitEvents).ConfigureAwait(false);
        this._pendingMessages = new();
        await context.SendMessageAsync(token).ConfigureAwait(false);
    }

    protected abstract ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellation = default);

    private const string PendingMessagesStateKey = nameof(_pendingMessages);
    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        Task messagesTask = Task.CompletedTask;
        if (this._pendingMessages.Count > 0)
        {
            JsonElement messagesValue = this._pendingMessages.Serialize();
            messagesTask = context.QueueStateUpdateAsync(PendingMessagesStateKey, messagesValue).AsTask();
        }

        await messagesTask.ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        JsonElement? messagesValue = await context.ReadStateAsync<JsonElement?>(PendingMessagesStateKey).ConfigureAwait(false);
        if (messagesValue.HasValue)
        {
            List<ChatMessage> messages = messagesValue.Value.DeserializeMessages();
            this._pendingMessages.AddRange(messages);
        }
    }
}
