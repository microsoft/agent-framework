// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Runtime;

// Implemented by the Agent Framework (eg, Agent, Orchestration, Process, etc)
/// <summary>
/// Represents an actor in the actor system that can process messages and maintain state.
/// </summary>
public interface IActor : IAsyncDisposable
{
    /// <summary>
    /// Runs the actor.
    /// When the value returned from this method completes, the actor is considered stopped.
    /// IActor is expected to call IActorContext.WatchMessagesAsync() to receive messages.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task representing the start operation.</returns>
    ValueTask RunAsync(CancellationToken cancellationToken);
}
