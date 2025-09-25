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
    private readonly Handoffs _handoffs;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestration"/> class.
    /// </summary>
    /// <param name="handoffs">Defines the handoff connections for each agent.</param>
    public HandoffOrchestration(Handoffs handoffs) : this(handoffs, name: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestration"/> class.
    /// </summary>
    /// <param name="handoffs">Defines the handoff connections for each agent.</param>
    /// <param name="name">An optional name for this orchestrating agent.</param>
    public HandoffOrchestration(Handoffs handoffs, string? name) : base(handoffs.Agents.ToArray(), name)
    {
        this._handoffs = handoffs;
    }

    /// <summary>Gets or sets a callback invoked when no next handoff is selected in order to supply </summary>
    public Func<ValueTask<ChatMessage>>? InteractiveCallback { get; set; }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage> allMessages = [.. messages];
        int originalMessageCount = allMessages.Count;
        return this.ResumeAsync(this._handoffs.InitialAgent, allMessages, originalMessageCount, context, cancellationToken);
    }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, IEnumerable<ChatMessage> newMessages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        var state = checkpointState.Deserialize(OrchestrationJsonContext.Default.HandoffState) ?? throw new InvalidOperationException("The checkpoint state is invalid.");

        AIAgent? nextAgent = null;
        if (state.NextAgent is null)
        {
            nextAgent = this._handoffs.InitialAgent;
        }
        else
        {
            nextAgent = this.Agents.FirstOrDefault(a => a.Id == state.NextAgent);
            if (nextAgent is null)
            {
                Throw.InvalidOperationException($"The next agent '{state.NextAgent}' is not defined in the orchestration.");
            }
        }

        // Append the new messages to the checkpoint state
        List<ChatMessage> allMessages = [.. state.AllMessages, .. newMessages];

        return this.ResumeAsync(nextAgent, allMessages, allMessages.Count, context, cancellationToken);
    }

    /// <inheritdoc />
    private async Task<AgentRunResponse> ResumeAsync(
        AIAgent? agent, List<ChatMessage> allMessages, int originalMessageCount, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        Debug.Assert(agent is not null);
        AgentRunResponse? response = null;

        while (agent is not null)
        {
            LogOrchestrationSubagentRunning(context, agent);

            if (!this._handoffs.Targets.TryGetValue(agent, out var handoffs) || handoffs.Count == 0)
            {
                // If no handoff is available, we can run the agent directly and return its response.
                response = await RunAsync(agent, context, allMessages, context.Options, cancellationToken).ConfigureAwait(false);
                LogOrchestrationSubagentCompleted(context, agent);
                allMessages.AddRange(response.Messages);
                agent = null;
                await CheckpointAsync().ConfigureAwait(false);
                break;
            }

            // Create the options for the next agent request, including handoff functions.
            HandoffContext handoffCtx = new(handoffs);
            ChatClientAgentRunOptions? options;
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
            LogOrchestrationSubagentCompleted(context, agent);
            allMessages.AddRange(response.Messages);
            agent = handoffCtx.TargetedAgent;
            RemoveHandoffFunctionCalls(response, handoffTools);

            if (this.InteractiveCallback is not null)
            {
                if (handoffCtx.EndTaskInvoked)
                {
                    break;
                }

                allMessages.Add(await this.InteractiveCallback().ConfigureAwait(false));
            }

            await CheckpointAsync().ConfigureAwait(false);
        }

        allMessages.RemoveRange(0, originalMessageCount);
        response ??= new();
        response.Messages = allMessages;
        return response;

        Task CheckpointAsync() => context.Runtime is not null ?
            WriteCheckpointAsync(JsonSerializer.SerializeToElement(new(agent?.Id, allMessages, originalMessageCount), OrchestrationJsonContext.Default.HandoffState), context, cancellationToken) :
            Task.CompletedTask;
    }

    private static void RemoveHandoffFunctionCalls(AgentRunResponse response, List<AITool> handoffTools)
    {
        HashSet<string>? removeToolNames = null;
        HashSet<string>? handoffCallIds = null;

        foreach (var message in response.Messages)
        {
            for (int i = message.Contents.Count - 1; i >= 0; i--)
            {
                if (message.Contents[i] is FunctionCallContent fcc)
                {
                    removeToolNames ??= [.. handoffTools.Select(t => t.Name)];
                    if (removeToolNames.Contains(fcc.Name))
                    {
                        (handoffCallIds ??= []).Add(fcc.CallId);
                        message.Contents.RemoveAt(i);
                    }
                }
            }
        }

        if (handoffCallIds is not null)
        {
            foreach (var message in response.Messages)
            {
                for (int i = message.Contents.Count - 1; i >= 0; i--)
                {
                    if (message.Contents[i] is FunctionResultContent frc && handoffCallIds.Contains(frc.CallId))
                    {
                        message.Contents.RemoveAt(i);
                    }
                }
            }
        }
    }

    private sealed class HandoffContext(HashSet<Handoffs.HandoffTarget> handoffs)
    {
        public AIAgent? TargetedAgent { get; set; }
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

            foreach (Handoffs.HandoffTarget handoff in handoffs)
            {
                functions.Add(AIFunctionFactory.Create(
                    () =>
                    {
                        this.TargetedAgent = handoff.Target;
                        Terminate();
                    },
                    name: $"handoff_to_{InvalidNameCharsRegex().Replace(handoff.Target.DisplayName, "_")}",
                    description: handoff.Reason));
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
