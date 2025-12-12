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

/// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandOffState"/> events.</summary>
internal sealed class HandOffAgentExecutor(
    AIAgent agent,
    string? handoffInstructions) : Executor(agent.GetDescriptiveId(), declareCrossRunShareable: true), IResettableExecutor
{
    private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
        ([Description("The reason for the handoff")] string? reasonForHandOff) => { }).JsonSchema;

    private readonly AIAgent _agent = agent;
    private readonly HashSet<string> _handoffFunctionNames = [];
    private ChatClientAgentRunOptions? _agentOptions;

    public void Initialize(
        WorkflowBuilder builder,
        Executor end,
        Dictionary<string, HandOffAgentExecutor> executors,
        HashSet<HandOffTarget> handoffs) =>
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
                foreach (HandOffTarget handoff in handoffs)
                {
                    index++;
                    var handoffFunc = AIFunctionFactory.CreateDeclaration($"{HandOffWorkflowBuilder.FunctionPrefix}{index}", handoff.Reason, s_handoffSchema);

                    this._handoffFunctionNames.Add(handoffFunc.Name);

                    this._agentOptions.ChatOptions.Tools.Add(handoffFunc);

                    sb.AddCase<HandOffState>(state => state?.InvokedHandOff == handoffFunc.Name, executors[handoff.Target.Id]);
                }
            }

            sb.WithDefault(end);
        });

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<HandOffState>(async (handoffState, context, cancellationToken) =>
        {
            string? requestedHandOff = null;
            List<AgentRunResponseUpdate> updates = [];
            List<ChatMessage> allMessages = handoffState.Messages;

            List<ChatMessage>? roleChanges = allMessages.ChangeAssistantToUserForOtherParticipants(this._agent.DisplayName);

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
                        requestedHandOff = fcc.Name;
                        await AddUpdateAsync(
                                new AgentRunResponseUpdate
                                {
                                    AgentId = this._agent.Id,
                                    AuthorName = this._agent.DisplayName,
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

            allMessages.AddRange(updates.ToAgentRunResponse().Messages);

            roleChanges.ResetUserToAssistantForChangedRoles();

            await context.SendMessageAsync(new HandOffState(handoffState.TurnToken, requestedHandOff, allMessages), cancellationToken: cancellationToken).ConfigureAwait(false);

            async Task AddUpdateAsync(AgentRunResponseUpdate update, CancellationToken cancellationToken)
            {
                updates.Add(update);
                if (handoffState.TurnToken.EmitEvents is true)
                {
                    await context.AddEventAsync(new AgentRunUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
                }
            }
        });

    public ValueTask ResetAsync() => default;
}
