// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using OpenAI.Chat;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;
using OpenAIChatClient = OpenAI.Chat.ChatClient;

namespace Microsoft.Agents.AI.OpenAI.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    [Fact]
    public async Task NonStreamingExecution_MarksOpenAIFeatureUsageAsync()
    {
        // Arrange
        Mock<IChatClient> innerClient = new();
        innerClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));
        var agent = new TestOpenAIChatClient().AsAIAgent(clientFactory: _ => innerClient.Object);
        FeatureUsageAssert.Reset();

        // Act
        _ = await agent.RunAsync("hello");

        // Assert
        FeatureUsageAssert.Marked(54);
    }

    [Fact]
    public async Task StreamingExecution_IsColdAndMarksOpenAIFeatureUsageAsync()
    {
        // Arrange
        Mock<IChatClient> innerClient = new();
        innerClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(EmptyUpdatesAsync());
        var agent = new TestOpenAIChatClient().AsAIAgent(clientFactory: _ => innerClient.Object);
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
        FeatureUsageAssert.Marked(54);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private static async IAsyncEnumerable<ChatResponseUpdate> EmptyUpdatesAsync()
    {
        await Task.CompletedTask;
        yield break;
    }

    private sealed class TestOpenAIChatClient : OpenAIChatClient;
}
