// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class ForwardMessageExecutor<TMessage>(string id) : Executor(id) where TMessage : notnull
{
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<TMessage>((message, ctx) => ctx.SendMessageAsync(message));
}
