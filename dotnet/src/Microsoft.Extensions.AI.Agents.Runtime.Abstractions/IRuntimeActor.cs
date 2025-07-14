// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents an actor within the runtime that can process messages, maintain state, and be closed when no longer needed.
/// </summary>
public interface IRuntimeActor : ISaveState
{
    /// <summary>
    /// Gets the unique identifier of the actor.
    /// </summary>
    ActorId Id { get; }

    /// <summary>
    /// Gets metadata associated with the actor.
    /// </summary>
    ActorMetadata Metadata { get; }

    /// <summary>
    /// Handles an incoming message for the actor.
    /// This should only be called by the runtime, not by other actors.
    /// </summary>
    /// <param name="message">The received message. The type should match one of the expected subscription types.</param>
    /// <param name="messageContext">The context of the message, providing additional metadata.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>
    /// A task representing the asynchronous operation, returning a response to the message.
    /// The response can be <c>null</c> if no reply is necessary.
    /// </returns>
    /// <exception cref="OperationCanceledException">Thrown if the message was canceled.</exception>
    ValueTask<object?> OnMessageAsync(object message, MessageContext messageContext, CancellationToken cancellationToken = default);
}
