// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
internal sealed class HandoffEndExecutor(bool returnToPrevious) : Executor(ExecutorId, declareCrossRunShareable: true), IResettableExecutor
{
    public const string ExecutorId = "HandoffEnd";

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<HandoffState>((handoff, context, cancellationToken) =>
                                            this.HandleAsync(handoff, context, cancellationToken)))
                       .YieldsOutput<List<ChatMessage>>();

    private async ValueTask HandleAsync(HandoffState handoff, IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (returnToPrevious)
        {
            await context.QueueStateUpdateAsync<string?>(HandoffConstants.PreviousAgentTrackerKey,
                                                         handoff.PreviousAgentId,
                                                         HandoffConstants.PreviousAgentTrackerScope,
                                                         cancellationToken)
                         .ConfigureAwait(false);
        }

        await context.YieldOutputAsync(handoff.Messages, cancellationToken).ConfigureAwait(false);
    }

    public ValueTask ResetAsync() => default;
}
