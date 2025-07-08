// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public class SendMessageTests
{
    [Fact]
    public async Task Test_SendMessage_ReturnsValueAsync()
    {
        static string ProcessFunc(string s) => $"Processed({s})";

        MessagingTestFixture fixture = new();

        await fixture.RegisterFactoryMapInstances(nameof(ProcessorAgent),
            (id, runtime) => new ValueTask<ProcessorAgent>(new ProcessorAgent(id, runtime, ProcessFunc, string.Empty)));

        AgentId targetAgent = new(nameof(ProcessorAgent), Guid.NewGuid().ToString());
        object? maybeResult = await fixture.RunSendTestAsync(targetAgent, new BasicMessage { Content = "1" });

        Assert.Equal("Processed(1)", Assert.IsType<BasicMessage>(maybeResult).Content);
    }

    [Fact]
    public async Task Test_SendMessage_CancellationAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterFactoryMapInstances(nameof(CancelAgent),
            (id, runtime) => new ValueTask<CancelAgent>(new CancelAgent(id, runtime, string.Empty)));

        AgentId targetAgent = new(nameof(CancelAgent), Guid.NewGuid().ToString());

        await Assert.ThrowsAsync<OperationCanceledException>(() => fixture.RunSendTestAsync(targetAgent, new BasicMessage { Content = "1" }).AsTask());
    }

    [Fact]
    public async Task Test_SendMessage_ErrorAsync()
    {
        MessagingTestFixture fixture = new();

        await fixture.RegisterFactoryMapInstances(nameof(ErrorAgent),
            (id, runtime) => new ValueTask<ErrorAgent>(new ErrorAgent(id, runtime, string.Empty)));

        AgentId targetAgent = new(nameof(ErrorAgent), Guid.NewGuid().ToString());

        await Assert.ThrowsAsync<TestException>(() => fixture.RunSendTestAsync(targetAgent, new BasicMessage { Content = "1" }).AsTask());
    }

    [Fact]
    public async Task Test_SendMessage_FromSendMessageHandlerAsync()
    {
        Guid[] targetGuids = [Guid.NewGuid(), Guid.NewGuid()];

        MessagingTestFixture fixture = new();

        Dictionary<AgentId, SendOnAgent> sendAgents = fixture.GetAgentInstances<SendOnAgent>();
        Dictionary<AgentId, ReceiverAgent> receiverAgents = fixture.GetAgentInstances<ReceiverAgent>();

        await fixture.RegisterFactoryMapInstances(nameof(SendOnAgent),
            (id, runtime) => new ValueTask<SendOnAgent>(new SendOnAgent(id, runtime, string.Empty, targetGuids)));

        await fixture.RegisterFactoryMapInstances(nameof(ReceiverAgent),
            (id, runtime) => new ValueTask<ReceiverAgent>(new ReceiverAgent(id, runtime, string.Empty)));

        AgentId targetAgent = new(nameof(SendOnAgent), Guid.NewGuid().ToString());
        BasicMessage input = new() { Content = "Hello" };
        Task testTask = fixture.RunSendTestAsync(targetAgent, input).AsTask();

        // We do not actually expect to wait the timeout here, but it is still better than waiting the 10 min
        // timeout that the tests default to. A failure will fail regardless of what timeout value we set.
        TimeSpan timeout = Debugger.IsAttached ? TimeSpan.FromSeconds(120) : TimeSpan.FromSeconds(10);
        Task timeoutTask = Task.Delay(timeout);

        Task completedTask = await Task.WhenAny([testTask, timeoutTask]);
        Assert.Same(testTask, completedTask);

        // Check that each of the target agents received the message
        foreach (Guid targetKey in targetGuids)
        {
            AgentId targetId = new(nameof(ReceiverAgent), targetKey.ToString());
            Assert.Single(receiverAgents[targetId].Messages);
            Assert.Contains(receiverAgents[targetId].Messages, m => m.Content == $"@{targetKey}: {input.Content}");
        }
    }
}
