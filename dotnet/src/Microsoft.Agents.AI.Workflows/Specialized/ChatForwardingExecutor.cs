// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor that forwards all messages.</summary>
internal sealed class ChatForwardingExecutor(string id) : Executor(id, declareCrossRunShareable: true), IResettableExecutor
{
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder
                .AddHandler<string>((message, context, cancellationToken) => context.SendMessageAsync(new ChatMessage(ChatRole.User, message), cancellationToken: cancellationToken))
                .AddHandler<ChatMessage>((message, context, cancellationToken) => context.SendMessageAsync(message, cancellationToken: cancellationToken))
                .AddHandler<List<ChatMessage>>((messages, context, cancellationToken) => context.SendMessageAsync(messages, cancellationToken: cancellationToken))
                .AddHandler<TurnToken>((turnToken, context, cancellationToken) => context.SendMessageAsync(turnToken, cancellationToken: cancellationToken));

    public ValueTask ResetAsync() => default;
}
