// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used at the end of a handoff workflow to raise a final completed event,
/// and in autonomous mode to loop control back to the source agent.</summary>
/// <remarks>
/// Autonomous-turn counters are tracked per source agent in <see cref="HandoffSharedState.AutonomousTurnsByAgent"/>.
/// On each invocation where the source agent did not request a handoff and termination has not fired,
/// the counter for that agent is incremented and control is sent back to that agent (via the
/// autonomous-return switch wired downstream of this executor). When the counter reaches the per-agent
/// turn limit — or when termination fires, or when autonomous mode is disabled for that agent — the
/// counter is reset to zero and the conversation is yielded as workflow output.
/// </remarks>
internal sealed class HandoffEndExecutor : Executor, IResettableExecutor
{
    public const string ExecutorId = "HandoffEnd";

    private readonly bool _returnToPrevious;
    private readonly bool _autonomousMode;
    private readonly int _autonomousTurnLimit;
    private readonly string _autonomousContinuationPrompt;
    private readonly HashSet<string>? _autonomousEnabledAgentIds;
    private readonly IReadOnlyDictionary<string, int> _autonomousTurnLimitsByAgentId;
    private readonly IReadOnlyDictionary<string, string> _autonomousContinuationPromptsByAgentId;

    private readonly StateRef<HandoffSharedState> _sharedStateRef = new(HandoffConstants.HandoffSharedStateKey,
                                                                        HandoffConstants.HandoffSharedStateScope);

    public HandoffEndExecutor(
        bool returnToPrevious,
        bool autonomousMode = false,
        int autonomousTurnLimit = HandoffWorkflowBuilderDefaults.DefaultAutonomousTurnLimit,
        string autonomousContinuationPrompt = HandoffWorkflowBuilderDefaults.DefaultAutonomousContinuationPrompt,
        HashSet<string>? autonomousEnabledAgentIds = null,
        IReadOnlyDictionary<string, int>? autonomousTurnLimitsByAgentId = null,
        IReadOnlyDictionary<string, string>? autonomousContinuationPromptsByAgentId = null)
        : base(ExecutorId, declareCrossRunShareable: true)
    {
        this._returnToPrevious = returnToPrevious;
        this._autonomousMode = autonomousMode;
        this._autonomousTurnLimit = autonomousTurnLimit;
        this._autonomousContinuationPrompt = autonomousContinuationPrompt;
        this._autonomousEnabledAgentIds = autonomousEnabledAgentIds;
        this._autonomousTurnLimitsByAgentId = autonomousTurnLimitsByAgentId ?? new Dictionary<string, int>();
        this._autonomousContinuationPromptsByAgentId = autonomousContinuationPromptsByAgentId ?? new Dictionary<string, string>();
    }

    private bool IsAutonomousEnabledFor(string agentId) =>
        // Null allow-list means every participant has autonomous mode enabled.
        this._autonomousEnabledAgentIds?.Contains(agentId) ?? true;

    private int TurnLimitFor(string agentId) =>
        this._autonomousTurnLimitsByAgentId.TryGetValue(agentId, out int limit) ? limit : this._autonomousTurnLimit;

    private string ContinuationPromptFor(string agentId) =>
        this._autonomousContinuationPromptsByAgentId.TryGetValue(agentId, out string? prompt) ? prompt : this._autonomousContinuationPrompt;

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        ProtocolBuilder pb = protocolBuilder
            .ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<HandoffState>(
                                                (handoff, context, cancellationToken) => this.HandleAsync(handoff, context, cancellationToken)))
            .YieldsOutput<List<ChatMessage>>();

        // Only advertise the outgoing-message capability when autonomous mode is enabled, since the
        // downstream return switch (Builder.AddSwitch on End) is only wired in that case.
        if (this._autonomousMode)
        {
            pb = pb.SendsMessage<HandoffState>();
        }

        return pb;
    }

    private async ValueTask HandleAsync(HandoffState handoff, IWorkflowContext context, CancellationToken cancellationToken)
    {
        await this._sharedStateRef.InvokeWithStateAsync(
            async (HandoffSharedState? sharedState, IWorkflowContext context, CancellationToken cancellationToken) =>
            {
                if (sharedState == null)
                {
                    throw new InvalidOperationException("Handoff Orchestration shared state was not properly initialized.");
                }

                // Autonomous mode: when the agent did not request a handoff and termination has not fired,
                // loop control back to the same agent (up to that agent's turn limit). Per-agent overrides
                // (enabled-agents allow-list, turn limit, continuation prompt) are honored here.
                bool canContinueAutonomously = this._autonomousMode
                                            && !handoff.IsTerminated
                                            && handoff.RequestedHandoffTargetAgentId is null
                                            && handoff.PreviousAgentId is not null
                                            && this.IsAutonomousEnabledFor(handoff.PreviousAgentId!);

                if (canContinueAutonomously)
                {
                    string agentId = handoff.PreviousAgentId!;
                    int turns = sharedState.AutonomousTurnsByAgent.TryGetValue(agentId, out int existing) ? existing : 0;
                    int limit = this.TurnLimitFor(agentId);

                    if (turns < limit)
                    {
                        sharedState.AutonomousTurnsByAgent[agentId] = turns + 1;

                        // Append a synthetic user message containing the continuation prompt so the agent
                        // has fresh input to act on for the next autonomous iteration.
                        sharedState.Conversation.AddMessage(new ChatMessage(ChatRole.User, this.ContinuationPromptFor(agentId))
                        {
                            CreatedAt = DateTimeOffset.UtcNow,
                            MessageId = Guid.NewGuid().ToString("N"),
                        });

                        // Send a HandoffState targeting the source agent. The downstream
                        // HandoffAutonomousReturnSwitch routes it to the matching agent executor.
                        HandoffState loopBack = new(
                            handoff.TurnToken,
                            RequestedHandoffTargetAgentId: agentId,
                            PreviousAgentId: agentId,
                            IsTerminated: false);

                        await context.SendMessageAsync(loopBack, cancellationToken).ConfigureAwait(false);

                        return sharedState;
                    }
                }

                // Terminal path: either termination fired, autonomous mode is disabled, or the turn
                // limit is reached. Reset this agent's autonomous counter so a subsequent user turn
                // starts fresh, then yield the conversation as workflow output.
                if (handoff.PreviousAgentId is not null)
                {
                    sharedState.AutonomousTurnsByAgent[handoff.PreviousAgentId] = 0;
                }

                if (this._returnToPrevious)
                {
                    sharedState.PreviousAgentId = handoff.PreviousAgentId;
                }

                await context.YieldOutputAsync(sharedState.Conversation.CloneHistory(), cancellationToken).ConfigureAwait(false);

                return sharedState;
            }, context, cancellationToken).ConfigureAwait(false);
    }

    public ValueTask ResetAsync() => default;
}
