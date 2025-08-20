// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Specialized;

internal class AIAgentHostExecutor : Executor
{
    private readonly AIAgent _agent;
    private readonly List<ChatMessage> _pendingMessages = new();
    private AgentThread? _thread = null;

    public AIAgentHostExecutor(AIAgent agent) : base(id: agent.Id)
    {
        this._agent = agent;
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
        // TODO: Ideally we want to be able to split the Run across multiple super-steps so that we can stream out
        // incremental updates from the chat model. 
        AgentRunResponse runResponse = await this._agent.RunAsync(this._pendingMessages, this.EnsureThread())
                                                        .ConfigureAwait(false);

        if (token.EmitEvents)
        {
            await context.AddEventAsync(new AgentRunEvent(this.Id, runResponse)).ConfigureAwait(false);
        }

        await context.SendMessageAsync(runResponse.Messages.ToList()).ConfigureAwait(false);
        await context.SendMessageAsync(token).ConfigureAwait(false);
    }
}
