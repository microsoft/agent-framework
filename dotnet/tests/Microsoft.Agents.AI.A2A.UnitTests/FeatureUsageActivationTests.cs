// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Moq;

namespace Microsoft.Agents.AI.A2A.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests() => FeatureUsageAssert.Reset();

    [Fact]
    public async Task RunAsync_ActivatesA2AAsync()
    {
        // Arrange
        A2AAgent agent = CreateAgent();

        // Act
        _ = await agent.RunAsync("hello");

        // Assert
        FeatureUsageAssert.Marked(62);
    }

    [Fact]
    public async Task RunStreamingAsync_IsColdAndActivatesA2AAsync()
    {
        // Arrange
        A2AAgent agent = CreateAgent();

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream = agent.RunStreamingAsync("hello");

        // Assert
        Assert.Equal(string.Empty, FeatureUsage.ApplyToUserAgent(string.Empty));
        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = stream.GetAsyncEnumerator();
        Assert.False(await enumerator.MoveNextAsync());
        FeatureUsageAssert.Marked(62);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private static A2AAgent CreateAgent()
    {
        Mock<IA2AClient> client = new();
        client
            .Setup(instance => instance.SendMessageAsync(
                It.IsAny<SendMessageRequest>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new SendMessageResponse
            {
                Message = new Message { MessageId = "response", Role = Role.Agent }
            });
        client
            .Setup(instance => instance.SendStreamingMessageAsync(
                It.IsAny<SendMessageRequest>(),
                It.IsAny<CancellationToken>()))
            .Returns(EmptyStreamAsync());

        return new A2AAgent(client.Object);
    }

    private static async IAsyncEnumerable<StreamResponse> EmptyStreamAsync()
    {
        await Task.CompletedTask;
        yield break;
    }
}
