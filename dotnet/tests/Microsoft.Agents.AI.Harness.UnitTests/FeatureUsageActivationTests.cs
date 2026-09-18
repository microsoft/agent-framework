// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

[Collection(nameof(HarnessFeatureUsageActivationTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests()
    {
        ResetFeatureUsage();
    }

    [Fact]
    public void Construction_DoesNotActivateHarnessOrCoreAgent()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        _ = new HarnessAgent(chatClient, CreateOptions());

        // Assert
        Assert.Null(GetFeatureToken());
    }

    [Fact]
    public async Task NonStreamingExecution_ActivatesHarnessAndDelegatedChatClientAgentAsync()
    {
        // Arrange
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, "done")]));
        var agent = new HarnessAgent(chatClient.Object, CreateOptions());

        // Act
        _ = await agent.RunAsync("hello");

        // Assert
        Assert.Equal("v1.3", GetFeatureToken());
    }

    [Fact]
    public async Task StreamingExecution_IsColdAndActivatesHarnessAndDelegatedChatClientAgentAsync()
    {
        // Arrange
        Mock<IChatClient> chatClient = new();
        chatClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(EmptyChatResponseUpdatesAsync());
        var agent = new HarnessAgent(chatClient.Object, CreateOptions());

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream = agent.RunStreamingAsync("hello");

        // Assert
        Assert.Null(GetFeatureToken());
        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = stream.GetAsyncEnumerator();
        Assert.False(await enumerator.MoveNextAsync());
        Assert.Equal("v1.3", GetFeatureToken());
    }

    public void Dispose()
    {
        ResetFeatureUsage();
    }

    private static string? GetFeatureToken()
        => (string?)typeof(FeatureUsage)
            .GetMethod("GetToken", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);

    private static void ResetFeatureUsage()
        => typeof(FeatureUsage)
            .GetMethod("ResetStateForTests", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, null);

    private static HarnessAgentOptions CreateOptions() => new()
    {
        DisableApprovalNotRequiredFunctionBypassing = true,
        DisableApprovalResponseBinding = true,
        DisableAgentModeProvider = true,
        DisableAgentSkillsProvider = true,
        DisableCompaction = true,
        DisableFileMemory = true,
        DisableOpenTelemetry = true,
        DisableTodoProvider = true,
        DisableToolAutoApproval = true,
        DisableWebSearch = true,
        ChatHistoryProvider = new NoOpChatHistoryProvider(),
    };

    private static async IAsyncEnumerable<ChatResponseUpdate> EmptyChatResponseUpdatesAsync()
    {
        await Task.CompletedTask;
        yield break;
    }

    private sealed class NoOpChatHistoryProvider : ChatHistoryProvider
    {
        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(
            InvokingContext context,
            CancellationToken cancellationToken = default)
            => new([]);

        protected override ValueTask StoreChatHistoryAsync(
            InvokedContext context,
            CancellationToken cancellationToken = default)
            => default;
    }
}

[CollectionDefinition(nameof(HarnessFeatureUsageActivationTestGroup), DisableParallelization = true)]
public sealed class HarnessFeatureUsageActivationTestGroup;
