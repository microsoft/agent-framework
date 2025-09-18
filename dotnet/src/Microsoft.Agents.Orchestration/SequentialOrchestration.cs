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

/// <summary>Provides an orchestration that passes messages sequentially through a series of agents.</summary>
public sealed partial class SequentialOrchestration : OrchestratingAgent
{
    /// <summary>Initializes a new instance of the <see cref="SequentialOrchestration"/> class.</summary>
    /// <param name="agents">The agents participating in the orchestration.</param>
    public SequentialOrchestration(params AIAgent[] agents) : this(agents, name: null)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="SequentialOrchestration"/> class.</summary>
    /// <param name="agents">The agents participating in the orchestration.</param>
    /// <param name="name">An optional name for this orchestrating agent.</param>
    public SequentialOrchestration(AIAgent[] agents, string? name) : base(agents, name)
    {
    }

    /// <inheritdoc />
    protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
        this.ResumeAsync(0, messages as IReadOnlyCollection<ChatMessage> ?? messages.ToList(), context, cancellationToken);

    /// <inheritdoc />
    protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, IEnumerable<ChatMessage> newMessages, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        var state = checkpointState.Deserialize(OrchestrationJsonContext.Default.SequentialState) ?? throw new InvalidOperationException("The checkpoint state is invalid.");

        // Append the new messages to the checkpoint state
        List<ChatMessage> allMessages = [.. state.Messages, .. newMessages];
        return this.ResumeAsync(state.Index, allMessages, context, cancellationToken);
    }

    /// <inheritdoc />
    private async Task<AgentRunResponse> ResumeAsync(int i, IReadOnlyCollection<ChatMessage> input, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        AgentRunResponse? response = null;
        for (; i < this.Agents.Count; i++)
        {
            LogOrchestrationSubagentRunning(context, this.Agents[i]);

            response = await RunAsync(this.Agents[i], context, input, options: null, cancellationToken).ConfigureAwait(false);
            input = response.Messages as IReadOnlyCollection<ChatMessage> ?? [.. response.Messages];

            await CheckpointAsync(i + 1, input, context, cancellationToken).ConfigureAwait(false);
        }

        Debug.Assert(response is not null, "Response should not be null after processing a positive number of agents.");
        return response!;
    }

    private static Task CheckpointAsync(int index, IReadOnlyCollection<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
        context.Runtime is not null ? WriteCheckpointAsync(JsonSerializer.SerializeToElement(new(index, messages), OrchestrationJsonContext.Default.SequentialState), context, cancellationToken) :
        Task.CompletedTask;

    internal sealed record SequentialState(int Index, IReadOnlyCollection<ChatMessage> Messages);
}
