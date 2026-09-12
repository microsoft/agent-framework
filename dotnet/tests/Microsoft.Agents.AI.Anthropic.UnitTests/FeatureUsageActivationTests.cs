// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Anthropic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Anthropic.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    [Fact]
    public async Task NonStreamingExecution_MarksAnthropicFeatureUsageAsync()
    {
        // Arrange
        Mock<IChatClient> innerClient = new();
        innerClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));
        var agent = Mock.Of<IAnthropicClient>().AsAIAgent(
            model: "test-model",
            clientFactory: _ => innerClient.Object);
        FeatureUsageAssert.Reset();

        // Act
        _ = await agent.RunAsync("hello");

        // Assert
        FeatureUsageAssert.Marked(55);
    }

    [Fact]
    public async Task StreamingExecution_IsColdAndMarksAnthropicFeatureUsageAsync()
    {
        // Arrange
        Mock<IChatClient> innerClient = new();
        innerClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(EmptyUpdatesAsync());
        var agent = Mock.Of<IAnthropicClient>().AsAIAgent(
            model: "test-model",
            clientFactory: _ => innerClient.Object);
        FeatureUsageAssert.Reset();

        // Act
        IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync("hello");

        // Assert
        innerClient.Verify(
            client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
        Assert.Equal(string.Empty, FeatureUsage.ApplyToUserAgent(string.Empty));

        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = updates.GetAsyncEnumerator();
        Assert.False(await enumerator.MoveNextAsync());
        innerClient.Verify(
            client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        FeatureUsageAssert.Marked(55);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private static async IAsyncEnumerable<ChatResponseUpdate> EmptyUpdatesAsync()
    {
        await Task.CompletedTask;
        yield break;
    }
}
