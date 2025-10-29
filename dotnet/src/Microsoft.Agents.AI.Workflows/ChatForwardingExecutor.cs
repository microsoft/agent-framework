// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// A ChatProtocol executor that forwards all messages it receives. Useful for splitting inputs into parallel
/// processing paths.
/// </summary>
/// <remarks>This executor is designed to be cross-run shareable and can be reset to its initial state. It handles
/// multiple chat-related types, enabling flexible message forwarding scenarios. Thread safety and reusability are
/// ensured by its design.</remarks>
/// <param name="id">The unique identifier for the executor instance. Used to distinguish this executor within the system.</param>
public sealed class ChatForwardingExecutor(string id) : Executor(id, declareCrossRunShareable: true), IResettableExecutor
{
    /// <inheritdoc/>
    protected sealed override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder
                .AddHandler<string>((message, context, cancellationToken) => context.SendMessageAsync(new ChatMessage(ChatRole.User, message), cancellationToken: cancellationToken))
                .AddHandler<ChatMessage>((message, context, cancellationToken) => context.SendMessageAsync(message, cancellationToken: cancellationToken))
                .AddHandler<List<ChatMessage>>((messages, context, cancellationToken) => context.SendMessageAsync(messages, cancellationToken: cancellationToken))
                .AddHandler<TurnToken>((turnToken, context, cancellationToken) => context.SendMessageAsync(turnToken, cancellationToken: cancellationToken));

    /// <inheritdoc/>
    public ValueTask ResetAsync() => default;
}
