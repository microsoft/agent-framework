// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the end of a handoff workflow to raise a final completed event.</summary>
internal sealed class HandoffEndExecutor(bool returnToPrevious) : Executor(ExecutorId, declareCrossRunShareable: true), IResettableExecutor
{
    public const string ExecutorId = "HandoffEnd";

    private readonly StateRef<HandoffSharedState> _sharedStateRef = new(HandoffConstants.HandoffSharedStateKey,
                                                                        HandoffConstants.HandoffSharedStateScope);

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
        protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<HandoffState>(
                                            (handoff, context, cancellationToken) => this.HandleAsync(handoff, context, cancellationToken)))
                       .YieldsOutput<List<ChatMessage>>();

    private async ValueTask HandleAsync(HandoffState handoff, IWorkflowContext context, CancellationToken cancellationToken)
    {
        await this._sharedStateRef.InvokeWithStateAsync(
            async (HandoffSharedState? sharedState, IWorkflowContext context, CancellationToken cancellationToken) =>
            {
                if (sharedState == null)
                {
                    throw new InvalidOperationException("Handoff Orchestration shared state was not properly initialized.");
                }

                if (returnToPrevious)
                {
                    sharedState.PreviousAgentId = handoff.PreviousAgentId;
                }

                await context.YieldOutputAsync(sharedState.Conversation.CloneAllMessages(), cancellationToken).ConfigureAwait(false);

                return sharedState;
            }, context, cancellationToken).ConfigureAwait(false);
    }

    public ValueTask ResetAsync() => default;
}
