﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration.Concurrent;

/// <summary>
/// Actor for capturing each <see cref="ConcurrentMessages.Result"/> message.
/// </summary>
internal sealed class ConcurrentResultActor : OrchestrationActor
{
    private readonly ConcurrentQueue<ConcurrentMessages.Result> _results;
    private readonly ActorType _orchestrationType;
    private readonly int _expectedCount;
    private int _resultCount;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConcurrentResultActor"/> class.
    /// </summary>
    /// <param name="id">The unique identifier of the agent.</param>
    /// <param name="runtime">The runtime associated with the agent.</param>
    /// <param name="context">The orchestration context.</param>
    /// <param name="orchestrationType">Identifies the orchestration agent.</param>
    /// <param name="expectedCount">The expected number of messages to be received.</param>
    /// <param name="logger">The logger to use for the actor</param>
    public ConcurrentResultActor(
        ActorId id,
        IAgentRuntime runtime,
        OrchestrationContext context,
        ActorType orchestrationType,
        int expectedCount,
        ILogger logger)
        : base(id, runtime, context, "Captures the results of the ConcurrentOrchestration", logger)
    {
        this._orchestrationType = orchestrationType;
        this._expectedCount = expectedCount;
        this._results = [];

        this.RegisterMessageHandler<ConcurrentMessages.Result>(this.HandleAsync);
    }

    private async ValueTask HandleAsync(ConcurrentMessages.Result item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.Logger.LogConcurrentResultCapture(this.Id, this._resultCount + 1, this._expectedCount);

        this._results.Enqueue(item);

        if (Interlocked.Increment(ref this._resultCount) == this._expectedCount)
        {
            await this.PublishMessageAsync(this._results.ToArray(), this._orchestrationType, cancellationToken).ConfigureAwait(false);
        }
    }
}
