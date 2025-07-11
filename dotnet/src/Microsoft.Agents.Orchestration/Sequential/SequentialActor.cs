// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration.Sequential;

/// <summary>
/// An actor used with the <see cref="SequentialOrchestration{TInput,TOutput}"/>.
/// </summary>
internal sealed class SequentialActor : AgentActor
{
    private readonly ActorType _nextAgent;

    /// <summary>
    /// Initializes a new instance of the <see cref="SequentialActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="Agent"/>.</param>
    /// <param name="nextAgent">The identifier of the next agent for which to handoff the result</param>
    /// <param name="logger">The logger to use for the actor</param>
    public SequentialActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, Agent agent, ActorType nextAgent, ILogger<SequentialActor>? logger = null)
        : base(id, runtime, context, agent, logger)
    {
        logger?.LogInformation("ACTOR {ActorId} {NextAgent}", this.Id, nextAgent);
        this._nextAgent = nextAgent;

        this.RegisterMessageHandler<SequentialMessages.Request>(this.HandleAsync);
        this.RegisterMessageHandler<SequentialMessages.Response>(this.HandleAsync);
    }

    public ValueTask HandleAsync(SequentialMessages.Request item, MessageContext messageContext, CancellationToken cancellationToken) =>
        this.InvokeAgentAsync(item.Messages, messageContext, cancellationToken);

    public ValueTask HandleAsync(SequentialMessages.Response item, MessageContext messageContext, CancellationToken cancellationToken) =>
        this.InvokeAgentAsync([item.Message], messageContext, cancellationToken);

    private async ValueTask InvokeAgentAsync(IList<ChatMessage> input, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogInformation("INVOKE {ActorId} {NextAgent}", this.Id, this._nextAgent);

        this.Logger.LogSequentialAgentInvoke(this.Id);

        ChatMessage response = await this.InvokeAsync(input, cancellationToken).ConfigureAwait(false);

        this.Logger.LogSequentialAgentResult(this.Id, response.Text);

        await this.PublishMessageAsync(response.AsResponseMessage(), this._nextAgent, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
