// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An <see cref="AgentActor"/> used with the <see cref="GroupChatOrchestration{TInput, TOutput}"/>.
/// </summary>
internal sealed class GroupChatAgentActor : AgentActor
{
    private readonly List<ChatMessage> _cache;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatAgentActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="AIAgent"/>.</param>
    /// <param name="logger">The logger to use for the actor</param>
    public GroupChatAgentActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, AIAgent agent, ILogger<GroupChatAgentActor>? logger = null)
        : base(id, runtime, context, agent, logger)
    {
        this._cache = [];

        this.RegisterMessageHandler<GroupChatMessages.Group>((item, ctx) => this._cache.AddRange(item.Messages));
        this.RegisterMessageHandler<GroupChatMessages.Reset>((item, ctx) => this.ResetThread());
        this.RegisterMessageHandler<GroupChatMessages.Speak>(this.HandleAsync);
    }

    private async ValueTask HandleAsync(GroupChatMessages.Speak item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogChatAgentInvoke(this.Id);

        ChatMessage response = await this.RunAsync(this._cache, cancellationToken).ConfigureAwait(false);

        this.Logger.LogChatAgentResult(this.Id, response.Text);

        this._cache.Clear();
        await this.PublishMessageAsync(new GroupChatMessages.Group([response]), this.Context.Topic, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
