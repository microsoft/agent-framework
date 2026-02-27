// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
internal sealed class HandoffsEndExecutor(HandoffsCurrentAgentTracker? tracker = null) : Executor(ExecutorId, declareCrossRunShareable: true), IResettableExecutor
{
    public const string ExecutorId = "HandoffEnd";

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<HandoffState>((handoff, context, cancellationToken) =>
                                            this.HandleAsync(handoff, context, cancellationToken)))
                       .YieldsOutput<List<ChatMessage>>();

    private async ValueTask HandleAsync(HandoffState handoff, IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (tracker is not null && handoff.CurrentAgentId is not null)
        {
            tracker.CurrentAgentId = handoff.CurrentAgentId;
        }

        await context.YieldOutputAsync(handoff.Messages, cancellationToken).ConfigureAwait(false);
    }

    public ValueTask ResetAsync() => default;
}
