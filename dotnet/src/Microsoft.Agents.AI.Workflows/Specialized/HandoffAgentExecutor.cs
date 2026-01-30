// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
internal sealed class HandoffAgentExecutor(
    AIAgent agent,
    string? handoffInstructions) : Executor(agent.GetDescriptiveId(), declareCrossRunShareable: true), IResettableExecutor
{
    private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
        ([Description("The reason for the handoff")] string? reasonForHandoff) => { }).JsonSchema;

    private readonly AIAgent _agent = agent;
    private readonly HashSet<string> _handoffFunctionNames = [];
    private ChatClientAgentRunOptions? _agentOptions;

    public void Initialize(
        WorkflowBuilder builder,
        Executor end,
        Dictionary<string, HandoffAgentExecutor> executors,
        HashSet<HandoffTarget> handoffs) =>
        builder.AddSwitch(this, sb =>
        {
            if (handoffs.Count != 0)
            {
                Debug.Assert(this._agentOptions is null);
                this._agentOptions = new()
                {
                    ChatOptions = new()
                    {
                        AllowMultipleToolCalls = false,
                        Instructions = handoffInstructions,
                        Tools = [],
                    },
                };

                int index = 0;
                foreach (HandoffTarget handoff in handoffs)
                {
                    index++;
                    var handoffFunc = AIFunctionFactory.CreateDeclaration($"{HandoffsWorkflowBuilder.FunctionPrefix}{index}", handoff.Reason, s_handoffSchema);

                    this._handoffFunctionNames.Add(handoffFunc.Name);

                    this._agentOptions.ChatOptions.Tools.Add(handoffFunc);

                    sb.AddCase<HandoffState>(state => state?.InvokedHandoff == handoffFunc.Name, executors[handoff.Target.Id]);
                }
            }

            sb.WithDefault(end);
        });

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<HandoffState>(async (handoffState, context, cancellationToken) =>
        {
            string? requestedHandoff = null;
            List<AgentResponseUpdate> updates = [];
            List<ChatMessage> allMessages = handoffState.Messages;

            List<ChatMessage>? roleChanges = allMessages.ChangeAssistantToUserForOtherParticipants(this._agent.Name ?? this._agent.Id);

            await foreach (var update in this._agent.RunStreamingAsync(allMessages,
                                                                       options: this._agentOptions,
                                                                       cancellationToken: cancellationToken)
                                                     .ConfigureAwait(false))
            {
                await AddUpdateAsync(update, cancellationToken).ConfigureAwait(false);

                foreach (var c in update.Contents)
                {
                    if (c is FunctionCallContent fcc && this._handoffFunctionNames.Contains(fcc.Name))
                    {
                        requestedHandoff = fcc.Name;
                        await AddUpdateAsync(
                                new AgentResponseUpdate
                                {
                                    AgentId = this._agent.Id,
                                    AuthorName = this._agent.Name ?? this._agent.Id,
                                    Contents = [new FunctionResultContent(fcc.CallId, "Transferred.")],
                                    CreatedAt = DateTimeOffset.UtcNow,
                                    MessageId = Guid.NewGuid().ToString("N"),
                                    Role = ChatRole.Tool,
                                },
                                cancellationToken
                             )
                            .ConfigureAwait(false);
                    }
                }
            }

            allMessages.AddRange(updates.ToAgentResponse().Messages);

            roleChanges.ResetUserToAssistantForChangedRoles();

            await context.SendMessageAsync(new HandoffState(handoffState.TurnToken, requestedHandoff, allMessages), cancellationToken: cancellationToken).ConfigureAwait(false);

            async Task AddUpdateAsync(AgentResponseUpdate update, CancellationToken cancellationToken)
            {
                updates.Add(update);
                if (handoffState.TurnToken.EmitEvents is true)
                {
                    await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
                }
            }
        });

    public ValueTask ResetAsync() => default;
}
