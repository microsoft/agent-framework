// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.UnitTests;

internal sealed class ForwardMessageExecutor<TMessage>(string? id = null) : Executor(id) where TMessage : notnull
{
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TMessage>((message, ctx) => ctx.SendMessageAsync(message));
}
