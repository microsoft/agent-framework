// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AGUI.WorkflowFailure;

/// <summary>
/// Creates the failing workflow used by the sample and its integration test.
/// </summary>
public static class FailingWorkflow
{
    /// <summary>
    /// Creates a workflow containing the supplied failing agent.
    /// </summary>
    /// <param name="agent">The agent that fails during execution.</param>
    /// <returns>The failing workflow.</returns>
    public static Workflow Create(AIAgent agent)
        => new SequentialWorkflowBuilder(agent).Build();
}

/// <summary>
/// An agent that throws a deterministic exception for the failure sample.
/// </summary>
public sealed class FailingAgent : AIAgent
{
    /// <inheritdoc />
    public override string? Name => "FailingStep";

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => throw new InvalidOperationException("The sample executor failed.");

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new AgentResponseUpdate(ChatRole.Assistant, "Starting work before failure.")
        {
            MessageId = "failure-message",
            ResponseId = "failure-response",
        };
        await Task.Yield();
        throw new InvalidOperationException("The sample executor failed.");
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new FailingSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new FailingSession());

    private sealed class FailingSession : AgentSession;
}
