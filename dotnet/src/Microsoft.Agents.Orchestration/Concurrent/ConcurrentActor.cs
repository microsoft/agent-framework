// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An <see cref="AgentActor"/> used with the <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
/// </summary>
internal sealed class ConcurrentActor : AgentActor
{
    private readonly ActorType _handoffActor;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConcurrentActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agent">An <see cref="AIAgent"/>.</param>
    /// <param name="resultActor">Identifies the actor collecting results.</param>
    /// <param name="logger">The logger to use for the actor</param>
    public ConcurrentActor(ActorId id, IAgentRuntime runtime, OrchestrationContext context, AIAgent agent, ActorType resultActor, ILogger<ConcurrentActor>? logger = null)
        : base(id, runtime, context, agent, logger)
    {
        this._handoffActor = resultActor;

        this.RegisterMessageHandler<ConcurrentMessages.Request>(this.HandleAsync);
    }

    private async ValueTask HandleAsync(ConcurrentMessages.Request item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogConcurrentAgentInvoke(this.Id);

        ChatMessage response = await this.RunAsync(item.Messages, cancellationToken).ConfigureAwait(false);

        this.Logger.LogConcurrentAgentResult(this.Id, response.Text);

        await this.PublishMessageAsync(new ConcurrentMessages.Result(response), this._handoffActor, cancellationToken).ConfigureAwait(false);
    }
}
