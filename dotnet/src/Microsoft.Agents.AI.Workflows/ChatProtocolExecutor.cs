// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal class ChatProtocolExecutorOptions
{
    public ChatRole? StringMessageChatRole { get; set; }
}

internal abstract class ChatProtocolExecutor(string id, ChatProtocolExecutorOptions? options = null) : Executor(id)
{
    private List<ChatMessage> _pendingMessages = [];
    private readonly ChatRole? _stringMessageChatRole = options?.StringMessageChatRole;

    // Note that we explicitly do not implement IResettableExecutor here, as we want to allow derived classes to
    // implement it if they want to be resettable, but do not want to opt them into it.
    protected ValueTask ResetAsync()
    {
        this._pendingMessages = [];
        return default;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        if (this._stringMessageChatRole.HasValue)
        {
            routeBuilder = routeBuilder.AddHandler<string>((message, _, __) => this._pendingMessages.Add(new(this._stringMessageChatRole.Value, message)));
        }

        // Routing requires exact type matches. The runtime may dispatch either List<ChatMessage> or ChatMessage[].
        return routeBuilder.AddHandler<ChatMessage>((message, _, __) => this._pendingMessages.Add(message))
                           .AddHandler<List<ChatMessage>>((messages, _, __) => this._pendingMessages.AddRange(messages))
                           .AddHandler<ChatMessage[]>((messages, _, __) => this._pendingMessages.AddRange(messages))
                           .AddHandler<TurnToken>(this.TakeTurnAsync);
    }

    public async ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await this.TakeTurnAsync(this._pendingMessages, context, token.EmitEvents, cancellationToken).ConfigureAwait(false);
        this._pendingMessages = [];
        await context.SendMessageAsync(token, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    protected abstract ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default);

    private const string PendingMessagesStateKey = nameof(_pendingMessages);
    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task messagesTask = Task.CompletedTask;
        if (this._pendingMessages.Count > 0)
        {
            JsonElement messagesValue = this._pendingMessages.Serialize();
            messagesTask = context.QueueStateUpdateAsync(PendingMessagesStateKey, messagesValue, cancellationToken: cancellationToken).AsTask();
        }

        await messagesTask.ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        JsonElement? messagesValue = await context.ReadStateAsync<JsonElement?>(PendingMessagesStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (messagesValue.HasValue)
        {
            List<ChatMessage> messages = messagesValue.Value.DeserializeMessages();
            this._pendingMessages.AddRange(messages);
        }
    }
}
