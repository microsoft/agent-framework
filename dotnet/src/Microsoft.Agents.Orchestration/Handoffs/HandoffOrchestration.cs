// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that provides the input message to the first agent
/// and sequentially passes each agent result to the next agent.
/// </summary>
public sealed partial class HandoffOrchestration : OrchestratingAgent
{
    private readonly OrchestrationHandoffs _handoffs;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestration"/> class.
    /// </summary>
    /// <param name="handoffs">Defines the handoff connections for each agent.</param>
    /// <param name="agents">Additional agents participating in the orchestration that weren't passed to <paramref name="handoffs"/>.</param>
    public HandoffOrchestration(OrchestrationHandoffs handoffs, params AIAgent[] agents) : base(
            agents is { Length: 0 } ? [.. handoffs.Agents] :
            handoffs.Agents is { Count: 0 } ? agents :
            [.. handoffs.Agents.Concat(agents).Distinct()])
    {
        // Create list of distinct agent names
        HashSet<string> agentNames = [.. base.Agents.Select(a => a.DisplayName), handoffs.FirstAgentName];

        // Extract names from handoffs that don't align with a member agent.
        // Fail fast if invalid names are present.
        string[] badNames = [.. handoffs.Keys.Concat(handoffs.Values.SelectMany(h => h.Keys)).Where(name => !agentNames.Contains(name))];
        if (badNames.Length > 0)
        {
            Throw.ArgumentException(nameof(handoffs), $"The following agents are not defined in the orchestration: {string.Join(", ", badNames)}");
        }

        this._handoffs = handoffs;
    }

    /// <summary>Gets or sets a callback invoked when no next handoff is selected in order to supply </summary>
    public Func<ValueTask<ChatMessage>>? InteractiveCallback { get; set; }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> RunCoreAsync(IReadOnlyCollection<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage> allMessages = [.. messages];
        int originalMessageCount = allMessages.Count;
        return this.ResumeAsync(this._handoffs.FirstAgentName, allMessages, originalMessageCount, context, cancellationToken);
    }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        var state = checkpointState.Deserialize(OrchestrationJsonContext.Default.HandoffState) ?? throw new InvalidOperationException("The checkpoint state is invalid.");
        return this.ResumeAsync(state.NextAgent, state.AllMessages, state.OriginalMessageCount, context, cancellationToken);
    }

    /// <inheritdoc />
    private async Task<AgentRunResponse> ResumeAsync(
        string? nextAgent, List<ChatMessage> allMessages, int originalMessageCount, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        Debug.Assert(nextAgent is not null);
        AgentRunResponse? response = null;

        while (nextAgent is not null)
        {
            AIAgent? agent =
                this.Agents.FirstOrDefault(a => a.Name == nextAgent || a.Id == nextAgent) ??
                throw new InvalidOperationException($"The agent '{nextAgent}' is not defined in the orchestration.");

            this.LogOrchestrationSubagentRunning(context, agent);

            if (!this._handoffs.TryGetValue(agent.DisplayName, out AgentHandoffs? handoffs) || handoffs.Count == 0)
            {
                // If no handoff is available, we can run the agent directly and return its response.
                response = await RunAsync(agent, context, allMessages, context.Options, cancellationToken).ConfigureAwait(false);
                allMessages.AddRange(response.Messages);
                nextAgent = null;
                await CheckpointAsync().ConfigureAwait(false);
                this.LogOrchestrationSubagentCompleted(context, agent);
                break;
            }

            // Create the options for the next agent request, including handoff functions.
            HandoffContext handoffCtx = new(handoffs);
            ChatClientAgentRunOptions? options = null;
            List<AITool> handoffTools = handoffCtx.CreateHandoffFunctions(this.InteractiveCallback is not null);
            if (context.Options is ChatClientAgentRunOptions contextOptions)
            {
                ChatOptions chatOptions = contextOptions.ChatOptions?.Clone() ?? new();
                chatOptions.Tools = chatOptions.Tools is { Count: > 0 } ? [.. chatOptions.Tools, .. handoffTools] : handoffTools;
                options = new(chatOptions);
            }
            else
            {
                options = new(new() { Tools = handoffTools });
            }

            // Invoke the next agent with all of the messages collected so far.
            response = await RunAsync(agent, context, allMessages, options, cancellationToken).ConfigureAwait(false);
            allMessages.AddRange(response.Messages);
            nextAgent = handoffCtx.TargetedAgent;
            RemoveHandoffFunctionCalls(response, handoffTools);

            if (this.InteractiveCallback is not null)
            {
                if (handoffCtx.EndTaskInvoked)
                {
                    break;
                }

                nextAgent = agent.DisplayName;
                allMessages.Add(await this.InteractiveCallback().ConfigureAwait(false));
            }

            await CheckpointAsync().ConfigureAwait(false);
            this.LogOrchestrationSubagentCompleted(context, agent);
        }

        allMessages.RemoveRange(0, originalMessageCount);
        response ??= new();
        response.Messages = allMessages;
        return response;

        Task CheckpointAsync() => context.Runtime is not null ?
            base.WriteCheckpointAsync(JsonSerializer.SerializeToElement(new(nextAgent, allMessages, originalMessageCount), OrchestrationJsonContext.Default.HandoffState), context, cancellationToken) :
            Task.CompletedTask;
    }

    private static void RemoveHandoffFunctionCalls(AgentRunResponse response, List<AITool> handoffTools)
    {
        HashSet<string>? removeToolNames = null;
        HashSet<string>? callIds = null;

        foreach (var message in response.Messages)
        {
            for (int i = message.Contents.Count - 1; i >= 0; i--)
            {
                if (message.Contents[i] is FunctionCallContent fcc)
                {
                    removeToolNames ??= [.. handoffTools.Select(t => t.Name)];
                    (callIds ??= new()).Add(fcc.CallId);

                    if (removeToolNames.Contains(fcc.Name))
                    {
                        message.Contents.RemoveAt(i);
                    }
                }
            }
        }

        if (callIds is not null)
        {
            foreach (var message in response.Messages)
            {
                for (int i = message.Contents.Count - 1; i >= 0; i--)
                {
                    if (message.Contents[i] is FunctionResultContent frc && callIds.Contains(frc.CallId))
                    {
                        message.Contents.RemoveAt(i);
                    }
                }
            }
        }
    }

    private sealed class HandoffContext(AgentHandoffs handoffs)
    {
        public string? TargetedAgent { get; set; }
        public bool EndTaskInvoked { get; set; }

        public List<AITool> CreateHandoffFunctions(bool needsEndTask)
        {
            List<AITool> functions = [];

            if (needsEndTask)
            {
                functions.Add(AIFunctionFactory.Create(
                    () =>
                    {
                        this.EndTaskInvoked = true;
                        Terminate();
                    },
                    name: "end_task",
                    description: "Invoke this function when all work is completed and no further interactions are required."));
            }

            foreach (KeyValuePair<string, string> handoff in handoffs)
            {
                functions.Add(AIFunctionFactory.Create(
                    () =>
                    {
                        this.TargetedAgent = handoff.Key;
                        Terminate();
                    },
                    name: $"handoff_to_{InvalidNameCharsRegex().Replace(handoff.Key, "_")}",
                    description: handoff.Value));
            }

            return functions;

            static void Terminate()
            {
                if (FunctionInvokingChatClient.CurrentContext is not { } ctx)
                {
                    throw new NotSupportedException($"The agent is not configured with a {nameof(FunctionInvokingChatClient)}. Cease execution.");
                }

                ctx.Terminate = true;
            }
        }
    }

    internal sealed record HandoffState(string? NextAgent, List<ChatMessage> AllMessages, int OriginalMessageCount);

    /// <summary>Regex that flags any character other than ASCII digits or letters or the underscore.</summary>
#if NET
    [GeneratedRegex("[^0-9A-Za-z_]+")]
    private static partial Regex InvalidNameCharsRegex();
#else
    private static Regex InvalidNameCharsRegex() => s_invalidNameCharsRegex;
    private static readonly Regex s_invalidNameCharsRegex = new("[^0-9A-Za-z_]+", RegexOptions.Compiled);
#endif
}
