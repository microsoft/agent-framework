// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
internal sealed class HandoffsEndExecutor() : Executor(ExecutorId, declareCrossRunShareable: true), IResettableExecutor
{
    public const string ExecutorId = "HandoffEnd";

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<HandoffState>((handoff, context, cancellationToken) =>
                                            context.YieldOutputAsync(handoff.Messages, cancellationToken)))
                       .YieldsOutput<List<ChatMessage>>();

    public ValueTask ResetAsync() => default;
}
