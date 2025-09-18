// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Orchestration;

/// <summary>Provides an orchestrating agent that broadcasts the input message to each agent and then aggregates the result into a single response.</summary>
public partial class ConcurrentOrchestration : OrchestratingAgent
{
    private Func<AgentRunResponse[], CancellationToken, Task<AgentRunResponse>>? _aggregationFunc;

    /// <summary>Initializes a new instance of the <see cref="ConcurrentOrchestration"/> class.</summary>
    /// <param name="subagents">The agents participating in the orchestration.</param>
    public ConcurrentOrchestration(params AIAgent[] subagents) : this(subagents, name: null)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="ConcurrentOrchestration"/> class.</summary>
    /// <param name="subagents">The agents participating in the orchestration.</param>
    /// <param name="name">An optional name for this orchestrating agent.</param>
    public ConcurrentOrchestration(AIAgent[] subagents, string? name) : base(subagents, name)
    {
    }

    /// <summary>Gets or sets the function to use to aggregate an <see cref="AgentRunResponse"/> from each participating agent into a single <see cref="AgentRunResponse"/>.</summary>
    /// <remarks>The default function takes the last message from each response and puts those messages into a new response instance.</remarks>
    public Func<AgentRunResponse[], CancellationToken, Task<AgentRunResponse>> AggregationFunc
    {
        get
        {
            if (this._aggregationFunc is { } f)
            {
                return f;
            }

            return (responses, cancellationToken)
                => Task.FromResult(
                    new AgentRunResponse([.. responses
                        .Where(r => r.Messages.Count > 0)
                        .Select(r =>
                        {
                            var messages = r.Messages;
                            return messages.Count > 0 ? messages[messages.Count - 1] : new();
                        })
                    ])
                );
        }
        set => this._aggregationFunc = value;
    }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
        this.ResumeAsync(messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList(), new AgentRunResponse?[this.Agents.Count], context, cancellationToken);

    /// <inheritdoc />
    protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, IEnumerable<ChatMessage> newMessages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        var state = checkpointState.Deserialize(OrchestrationJsonContext.Default.ConcurrentState) ?? throw new InvalidOperationException("The checkpoint state is invalid.");

        // Append the new messages to the checkpoint state
        List<ChatMessage> allMessages = [.. state.Messages, .. newMessages];
        return this.ResumeAsync(allMessages, state.Completed, context, cancellationToken);
    }

    /// <inheritdoc />
    private async Task<AgentRunResponse> ResumeAsync(
        IReadOnlyCollection<ChatMessage> input, AgentRunResponse?[] completed, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        List<Task> tasks = new(this.Agents.Count);
        for (int i = 0; i < this.Agents.Count; i++)
        {
            if (completed[i] is null)
            {
                int localI = i;
                tasks.Add(Task.Run(async () =>
                {
                    AIAgent agent = this.Agents[localI];
                    LogOrchestrationSubagentRunning(context, agent);

                    completed[localI] = await RunAsync(agent, context, input, options: null, cancellationToken).ConfigureAwait(false);

                    LogOrchestrationSubagentCompleted(context, agent);
                    await CheckpointAsync(input, completed, context, cancellationToken).ConfigureAwait(false);
                }, cancellationToken));
            }
        }

        // TODO: What do we want to do if one of the agents fails? As written, this waits for all to complete,
        // and then throws. And when resumption happens, it'll end up retrying failed agents. If we don't want that,
        // which we probably don't, we should checkpoint that failures happened, too.

        await Task.WhenAll(tasks).ConfigureAwait(false);

        Debug.Assert(Array.TrueForAll(completed, r => r is not null), "Expected all agents to have produced a result");
        return await this.AggregationFunc(completed!, cancellationToken).ConfigureAwait(false);
    }

    private static Task CheckpointAsync(IReadOnlyCollection<ChatMessage> messages, AgentRunResponse?[] completed, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
        context.Runtime is not null ? WriteCheckpointAsync(JsonSerializer.SerializeToElement(new(messages, completed), OrchestrationJsonContext.Default.ConcurrentState), context, cancellationToken) :
        Task.CompletedTask;

    internal sealed record ConcurrentState(IReadOnlyCollection<ChatMessage> Messages, AgentRunResponse?[] Completed);
}
