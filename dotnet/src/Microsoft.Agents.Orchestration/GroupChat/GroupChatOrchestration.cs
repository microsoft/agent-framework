// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that coordinates a group-chat using a manager to control conversation flow.
/// </summary>
public sealed partial class GroupChatOrchestration : OrchestratingAgent
{
    private readonly GroupChatManager _manager;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatOrchestration"/> class.
    /// </summary>
    /// <param name="manager">The manager that controls the flow of the group-chat.</param>
    /// <param name="agents">The agents participating in the orchestration.</param>
    public GroupChatOrchestration(GroupChatManager manager, params AIAgent[] agents) : this(manager, agents, name: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatOrchestration"/> class.
    /// </summary>
    /// <param name="manager">The manager that controls the flow of the group-chat.</param>
    /// <param name="agents">The agents participating in the orchestration.</param>
    /// <param name="name">An optional name for this orchestrating agent.</param>
    public GroupChatOrchestration(GroupChatManager manager, AIAgent[] agents, string? name) : base(agents, name)
    {
        this._manager = Throw.IfNull(manager);
    }

    /// <summary>Gets or sets a callback invoked when user input is requested.</summary>
    public Func<ValueTask<ChatMessage>>? InteractiveCallback { get; set; }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage> allMessages = [.. messages];
        int originalMessageCount = allMessages.Count;
        return this.ResumeAsync(allMessages, originalMessageCount, context, cancellationToken);
    }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, IEnumerable<ChatMessage> newMessages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        var state = checkpointState.Deserialize(OrchestrationJsonContext.Default.GroupChatState) ?? throw new InvalidOperationException("The checkpoint state is invalid.");

        // Append the new messages to the checkpoint state
        List<ChatMessage> allMessages = [.. state.AllMessages, .. newMessages];

        return this.ResumeAsync(allMessages, allMessages.Count, context, cancellationToken);
    }

    private async Task<AgentRunResponse> ResumeAsync(
        List<ChatMessage> allMessages, int originalMessageCount, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        GroupChatTeam team = [];
        foreach (AIAgent agent in this.Agents)
        {
            team[agent.DisplayName] = (agent.GetType().Name, agent.Description ?? agent.Name ?? "A helpful agent.");
        }

        var interactiveCallback = this.InteractiveCallback ?? this._manager.InteractiveCallback;
        while (true)
        {
            // First, check if we should request user input.
            if (interactiveCallback is not null)
            {
                var userInputResult = await this._manager.ShouldRequestUserInputAsync(allMessages, cancellationToken).ConfigureAwait(false);
                if (userInputResult.Value && interactiveCallback is not null)
                {
                    ChatMessage userMessage = await interactiveCallback().ConfigureAwait(false);
                    allMessages.Add(userMessage);

                    // Broadcast the user input
                    if (this.ResponseCallback is not null)
                    {
                        await this.ResponseCallback([userMessage]).ConfigureAwait(false);
                    }

                    await CheckpointAsync(allMessages, originalMessageCount, context, cancellationToken).ConfigureAwait(false);
                    continue;
                }
            }

            // Check if we should terminate the conversation
            var terminateResult = await this._manager.ShouldTerminateAsync(allMessages, cancellationToken).ConfigureAwait(false);
            if (terminateResult.Value)
            {
                // Filter and return final results
                var filterResult = await this._manager.FilterResultsAsync(allMessages, cancellationToken).ConfigureAwait(false);
                return new AgentRunResponse([new ChatMessage(ChatRole.Assistant, filterResult.Value) { AuthorName = this.DisplayName }]);
            }

            // Select the next agent to speak
            var nextAgentResult = await this._manager.SelectNextAgentAsync(allMessages, team, cancellationToken).ConfigureAwait(false);
            AIAgent nextAgent = this.FindAgentByName(nextAgentResult.Value) ??
                throw new InvalidOperationException($"AIAgent '{nextAgentResult.Value}' not found in the orchestration.");

            // Run the selected agent with all messages.
            LogOrchestrationSubagentRunning(context, nextAgent);
            AgentRunResponse response = await RunAsync(nextAgent, context, allMessages, options: null, cancellationToken).ConfigureAwait(false);
            allMessages.AddRange(response.Messages); // Add the agent's response to the conversation.
            LogOrchestrationSubagentCompleted(context, nextAgent);

            await CheckpointAsync(allMessages, originalMessageCount, context, cancellationToken).ConfigureAwait(false);
        }
    }

    private AIAgent? FindAgentByName(string name) => this.Agents.FirstOrDefault(a => a.DisplayName == name);

    private static Task CheckpointAsync(List<ChatMessage> allMessages, int originalMessageCount, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
        context.Runtime is not null ? WriteCheckpointAsync(JsonSerializer.SerializeToElement(new(allMessages, originalMessageCount), OrchestrationJsonContext.Default.GroupChatState), context, cancellationToken) :
        Task.CompletedTask;

    internal sealed record GroupChatState(List<ChatMessage> AllMessages, int OriginalMessageCount);
}
