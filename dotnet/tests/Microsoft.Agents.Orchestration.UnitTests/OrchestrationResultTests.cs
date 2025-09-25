// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Orchestration.UnitTest;

public class OrchestrationResultTests
{
    [Fact]
    public async Task ConstructorInitializesPropertiesCorrectlyAsync()
    {
        // Arrange
        OrchestratingAgentContext context = new()
        {
            OrchestratingAgent = new MockOrchestratingAgent(),
        };
        TaskCompletionSource<AgentRunResponse> tcs = new();

        // Act
        using CancellationTokenSource cancelSource = new();
        await using OrchestratingAgentResponse result = new(context, tcs.Task, cancelSource, NullLogger.Instance);

        // Assert
        Assert.Same(context, result.Context);
        Assert.Same(tcs.Task, result.Task);
    }

    [Fact]
    public async Task GetValueAsyncReturnsCompletedValueWhenTaskIsCompletedAsync()
    {
        // Arrange
        OrchestratingAgentContext context = new()
        {
            OrchestratingAgent = new MockOrchestratingAgent(),
        };
        TaskCompletionSource<AgentRunResponse> tcs = new();
        using CancellationTokenSource cancelSource = new();
        await using OrchestratingAgentResponse result = new(context, tcs.Task, cancelSource, NullLogger.Instance);
        AgentRunResponse expectedValue = new();

        // Act
        tcs.SetResult(expectedValue);

        // Assert
        Assert.Same(expectedValue, await result);
    }

    [Fact]
    public async Task GetValueAsyncReturnsCompletedValueWhenCompletionIsDelayedAsync()
    {
        // Arrange
        OrchestratingAgentContext context = new()
        {
            OrchestratingAgent = new MockOrchestratingAgent(),
        };

        TaskCompletionSource<AgentRunResponse> tcs = new();
        using CancellationTokenSource cancelSource = new();
        await using OrchestratingAgentResponse result = new(context, tcs.Task, cancelSource, NullLogger.Instance);
        AgentRunResponse expectedValue = new();

        // Act
        // Simulate delayed completion in a separate task
        Task delayTask = Task.Run(async () =>
        {
            await Task.Delay(100);
            tcs.SetResult(expectedValue);
        });

        // Assert
        Assert.Same(expectedValue, await result);
    }

    private sealed class MockOrchestratingAgent() : OrchestratingAgent([new MockAgent()])
    {
        protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
            throw new NotSupportedException();

        protected override Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, IEnumerable<ChatMessage> newMessages, OrchestratingAgentContext context, CancellationToken cancellationToken) =>
            throw new NotSupportedException();
    }

    private sealed class MockAgent : AIAgent
    {
        public override AgentThread GetNewThread()
            => throw new NotSupportedException();
        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => throw new NotSupportedException();
        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
        public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
    }
}
