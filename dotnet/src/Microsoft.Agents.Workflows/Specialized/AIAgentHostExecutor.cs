// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Specialized;

internal class AIAgentHostExecutor : Executor
{
    private readonly bool _emitEvents;
    private readonly AIAgent _agent;
    private readonly List<ChatMessage> _pendingMessages = new();
    private AgentThread? _thread = null;

    public AIAgentHostExecutor(AIAgent agent, bool emitEvents = false) : base(id: agent.Id)
    {
        this._agent = agent;
        this._emitEvents = emitEvents;
    }

    private AgentThread EnsureThread()
    {
        if (this._thread != null)
        {
            return this._thread;
        }

        return this._thread = this._agent.GetNewThread();
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder.AddHandler<ChatMessage>(this.QueueMessageAsync)
                           .AddHandler<List<ChatMessage>>(this.QueueMessagesAsync)
                           .AddHandler<TurnToken>(this.TakeTurnAsync);
    }

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

    public async ValueTask TakeTurnAsync(TurnToken token, IWorkflowContext context)
    {
        bool emitEvents = token.EmitEvents.HasValue ? token.EmitEvents.Value : this._emitEvents;
        IAsyncEnumerable<AgentRunResponseUpdate> agentStream = this._agent.RunStreamingAsync(this._pendingMessages, this.EnsureThread());

        List<AgentRunResponseUpdate> updates = new();
        await foreach (AgentRunResponseUpdate update in agentStream.ConfigureAwait(false))
        {
            if (emitEvents)
            {
                await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update)).ConfigureAwait(false);
            }

            // TODO: FunctionCall request handling, and user info request handling.
            // In some sense: We should just let it be handled as a ChatMessage, though we should consider
            // providing some mechanisms to help the user complete the request, or route it out of the
            // workflow.

            updates.Add(update);
            ChatMessage message = new(update.Role ?? ChatRole.Assistant, update.Contents)
            {
                AuthorName = update.AuthorName,
                CreatedAt = update.CreatedAt,
                MessageId = update.MessageId,
                RawRepresentation = update.RawRepresentation,
                AdditionalProperties = update.AdditionalProperties
            };

            await context.SendMessageAsync(message).ConfigureAwait(false);
        }

        await context.SendMessageAsync(token).ConfigureAwait(false);
    }
}
