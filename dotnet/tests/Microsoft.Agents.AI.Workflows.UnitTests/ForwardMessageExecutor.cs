// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class ForwardMessageExecutor<TMessage>(string id) : Executor(id) where TMessage : notnull
{
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        protocolBuilder.RouteBuilder.AddHandler<TMessage>((message, ctx) => ctx.SendMessageAsync(message));

        return protocolBuilder.SendsMessage<TMessage>();
    }
}
