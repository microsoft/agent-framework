// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
internal sealed class HandoffAgentExecutor(
    AIAgent agent,
    string? handoffInstructions) : Executor<HandoffState, HandoffState>(agent.GetDescriptiveId(), declareCrossRunShareable: true), IResettableExecutor
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

    public override async ValueTask<HandoffState> HandleAsync(HandoffState message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string? requestedHandoff = null;
        List<AgentResponseUpdate> updates = [];
        List<ChatMessage> allMessages = message.Messages;

        List<ChatMessage>? roleChanges = allMessages.ChangeAssistantToUserForOtherParticipants(this._agent.Name ?? this._agent.Id);

        // If a handoff was invoked by a previous agent, filter out the handoff function
        // call and tool result messages before sending to the underlying agent. These
        // are internal workflow mechanics that confuse the target model into ignoring the
        // original user question.
        List<ChatMessage> messagesForAgent = message.InvokedHandoff is not null
            ? FilterHandoffMessages(allMessages)
            : allMessages;

        await foreach (var update in this._agent.RunStreamingAsync(messagesForAgent,
                                                                   options: this._agentOptions,
                                                                   cancellationToken: cancellationToken)
                                                .ConfigureAwait(false))
        {
            await AddUpdateAsync(update, cancellationToken).ConfigureAwait(false);

            foreach (var fcc in update.Contents.OfType<FunctionCallContent>()
                                               .Where(fcc => this._handoffFunctionNames.Contains(fcc.Name)))
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

        allMessages.AddRange(updates.ToAgentResponse().Messages);

        roleChanges.ResetUserToAssistantForChangedRoles();

        return new(message.TurnToken, requestedHandoff, allMessages);

        async Task AddUpdateAsync(AgentResponseUpdate update, CancellationToken cancellationToken)
        {
            updates.Add(update);
            if (message.TurnToken.EmitEvents is true)
            {
                await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Creates a filtered copy of the message list with handoff function call contents and
    /// tool result messages removed, preserving any non-handoff content in mixed messages.
    /// </summary>
    private static List<ChatMessage> FilterHandoffMessages(List<ChatMessage> messages)
    {
        List<ChatMessage> filtered = [];
        foreach (ChatMessage m in messages)
        {
            if (m.Role == ChatRole.Tool && m.Contents.Any(c => c is FunctionResultContent))
            {
                continue;
            }

            if (m.Role == ChatRole.Assistant && m.Contents.Any(c => c is FunctionCallContent))
            {
                List<AIContent> filteredContents = m.Contents
                    .Where(c => c is not FunctionCallContent)
                    .ToList();

                if (filteredContents.Count > 0)
                {
                    filtered.Add(new ChatMessage(m.Role, filteredContents) { AuthorName = m.AuthorName });
                }

                continue;
            }

            filtered.Add(m);
        }

        return filtered;
    }

    public ValueTask ResetAsync() => default;
}
