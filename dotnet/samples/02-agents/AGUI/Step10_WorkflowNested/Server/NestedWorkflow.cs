// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace AGUI.WorkflowNested;

/// <summary>
/// Creates parallel nested workflows with duplicate local executor IDs.
/// </summary>
public static class NestedWorkflow
{
    /// <summary>
    /// Creates the parent workflow.
    /// </summary>
    /// <returns>A parent workflow containing security and style subworkflows.</returns>
    public static Workflow Create()
    {
        AnalysisGate gate = new();
        ChatForwardingExecutor start = new("Start");
        ExecutorBinding security = CreateAnalysisWorkflow("Security", gate).BindAsExecutor("SecurityPipeline");
        ExecutorBinding style = CreateAnalysisWorkflow("Style", gate).BindAsExecutor("StylePipeline");

        return new WorkflowBuilder(start)
            .AddFanOutEdge(start, [security, style])
            .WithOutputFrom(security, style)
            .Build();
    }

    private static Workflow CreateAnalysisWorkflow(string analysisType, AnalysisGate gate)
        => new SequentialWorkflowBuilder(new AnalysisAgent(analysisType, gate)).Build();
}

internal sealed class AnalysisAgent(string analysisType, AnalysisGate gate) : AIAgent
{
    protected override string? IdCore => "Analyze";

    public override string? Name => "Analyze";

    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => Task.FromResult(new AgentResponse(
            new ChatMessage(ChatRole.Assistant, $"{analysisType} analysis complete.")));

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await gate.SignalAndWaitAsync(cancellationToken).ConfigureAwait(false);
        yield return new AgentResponseUpdate(ChatRole.Assistant, $"{analysisType} analysis complete.")
        {
            MessageId = $"{analysisType}-message",
            ResponseId = $"{analysisType}-response",
        };
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new AnalysisSession());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new Dictionary<string, string>()));

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new AnalysisSession());

    private sealed class AnalysisSession : AgentSession;
}

internal sealed class AnalysisGate
{
    private readonly TaskCompletionSource _bothStarted = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private int _startedCount;

    public async Task SignalAndWaitAsync(CancellationToken cancellationToken)
    {
        if (Interlocked.Increment(ref this._startedCount) == 2)
        {
            this._bothStarted.TrySetResult();
        }

        await this._bothStarted.Task.WaitAsync(cancellationToken).ConfigureAwait(false);
    }
}
