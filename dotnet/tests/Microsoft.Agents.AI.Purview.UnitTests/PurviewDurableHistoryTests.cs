// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Purview.UnitTests;

/// <summary>
/// Pins what becomes durable history when Purview is composed at the chat-client level.
/// The agent persists the response its chat client returned, and Purview has already
/// replaced a blocked response by then, so the replacement is what is stored and the
/// model's own content never reaches the history provider.
/// </summary>
public sealed class PurviewDurableHistoryTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChatLevelBlockedResponseDoesNotBecomeDurableHistoryAsync(bool streaming)
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var agent = CreateAgent(promptBlocked: false, responseBlocked: true, provider);
        var session = await agent.CreateSessionAsync();

        // Act
        var text = await RunAsync(agent, session, streaming);

        // Assert
        Assert.Contains("Response blocked by policy", text);
        Assert.DoesNotContain(provider.Stored, message => message.Text.Contains("Sensitive response"));
        Assert.Contains(provider.Stored, message => message.Text.Contains("Response blocked by policy"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChatLevelAllowedResponseStillBecomesDurableHistoryAsync(bool streaming)
    {
        // Arrange
        var provider = new RecordingHistoryProvider();
        var agent = CreateAgent(promptBlocked: false, responseBlocked: false, provider);
        var session = await agent.CreateSessionAsync();

        // Act
        var text = await RunAsync(agent, session, streaming);

        // Assert
        Assert.Contains("Sensitive response", text);
        Assert.Contains(provider.Stored, message => message.Text.Contains("Sensitive response"));
    }

    private static async Task<string> RunAsync(AIAgent agent, AgentSession session, bool streaming)
    {
        var message = new ChatMessage(ChatRole.User, "Test message");
        if (!streaming)
        {
            return (await agent.RunAsync(message, session)).Text;
        }

        var text = string.Empty;
        await foreach (var update in agent.RunStreamingAsync(message, session))
        {
            text += update.Text;
        }

        return text;
    }

    private static ChatClientAgent CreateAgent(bool promptBlocked, bool responseBlocked, ChatHistoryProvider provider)
    {
        var settings = new PurviewSettings("TestApp")
        {
            TenantId = "tenant-123",
            PurviewAppLocation = new PurviewAppLocation(PurviewLocationType.Application, "app-123"),
            BlockedPromptMessage = "Prompt blocked by policy",
            BlockedResponseMessage = "Response blocked by policy"
        };

        var processor = new Mock<IScopedContentProcessor>();
        processor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            Activity.UploadText,
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((promptBlocked, "user-123"));
        processor.Setup(x => x.ProcessMessagesAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<string>(),
            Activity.DownloadText,
            It.IsAny<PurviewSettings>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((responseBlocked, "user-123"));

        var wrapper = new PurviewWrapper(processor.Object, settings, NullLogger.Instance, Mock.Of<IBackgroundJobRunner>());

        var innerClient = new Mock<IChatClient>();
        innerClient.Setup(x => x.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<ChatOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant, "Sensitive response")));

        return new ChatClientAgent(
            new PurviewChatClient(innerClient.Object, wrapper),
            new ChatClientAgentOptions { ChatHistoryProvider = provider });
    }

    /// <summary>A chat history provider that records exactly what becomes durable.</summary>
    private sealed class RecordingHistoryProvider : ChatHistoryProvider
    {
        public List<ChatMessage> Stored { get; } = [];

        protected override ValueTask<IEnumerable<ChatMessage>> ProvideChatHistoryAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
            new([.. this.Stored]);

        protected override ValueTask StoreChatHistoryAsync(InvokedContext context, CancellationToken cancellationToken = default)
        {
            this.Stored.AddRange(context.RequestMessages);
            this.Stored.AddRange(context.ResponseMessages ?? []);
            return default;
        }
    }
}
