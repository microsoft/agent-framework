// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal enum ChatRoleType
{
    None,
    User,
    Assistant,
    Custom
}

internal static class ChatRoleTestingExtensions
{
    public const string CustomChatRoleName = nameof(CustomChatRole);

    public static ChatRole CustomChatRole { get; } = new(CustomChatRoleName);

    public static ChatRole? ToChatRole(this ChatRoleType type)
        => type switch
        {
            ChatRoleType.None => null,
            ChatRoleType.User => ChatRole.User,
            ChatRoleType.Assistant => ChatRole.Assistant,
            ChatRoleType.Custom => CustomChatRole,
            _ => throw new ArgumentOutOfRangeException(
                nameof(type),
                type,
                $"Invalid ChatRoleType {type}; expecting one of {string.Join(",",
                                                                    [null,
                                                                     ChatRole.User,
                                                                     ChatRole.Assistant,
                                                                     CustomChatRole])}")
        };
}

public class ChatForwardingExecutorTests
{
    private async Task<TestWorkflowContext> RunForwardMessageTestAsync<TMessage>(ChatForwardingExecutor executor, TMessage message)
        where TMessage : notnull
    {
        // Ensure that we have constructed the Protocol (and registered the handlers)
        _ = executor.Protocol;

        TestWorkflowContext testContext = new(executor.Id);
        object? callResult = await executor.ExecuteCoreAsync(message, new TypeId(typeof(TMessage)), testContext);

        Assert.Null(callResult); // ChatForwardingExecutor's do not have a return type

        return testContext;
    }

    private const string TestMessageContent = nameof(TestMessageContent);

    [Fact]
    public async Task Test_ChatForwardingExecutor_DoesNotForwardStringByDefaultAsync()
    {
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));

        // Act
        Task<TestWorkflowContext> actionAsync() => this.RunForwardMessageTestAsync(executor, TestMessageContent);
        await Assert.ThrowsAsync<NotSupportedException>((Func<Task<TestWorkflowContext>>)actionAsync);
    }

    [Theory]
    [InlineData(ChatRoleType.None)]
    [InlineData(ChatRoleType.User)]
    [InlineData(ChatRoleType.Assistant)]
    [InlineData(ChatRoleType.Custom)]
    internal async Task Test_ChatForwardingExecutor_ForwardsStringIfConfiguredAsync(ChatRoleType chatRoleType)
    {
        // Arrange
        ChatForwardingExecutorOptions options = new()
        {
            StringMessageChatRole = chatRoleType.ToChatRole()
        };

        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor), options);

        // Act
        Task<TestWorkflowContext> actionAsync() => this.RunForwardMessageTestAsync(executor, TestMessageContent);

        // Assert
        if (options.StringMessageChatRole is ChatRole chatRole)
        {
            TestWorkflowContext testContext = await actionAsync();

            ChatMessage sentMessage = Assert.IsType<ChatMessage>(Assert.Single(testContext.SentMessages));
            Assert.Equivalent(new ChatMessage(chatRole, TestMessageContent), sentMessage);
        }
        else
        {
            await Assert.ThrowsAsync<NotSupportedException>((Func<Task<TestWorkflowContext>>)actionAsync);
        }
    }

    [Fact]
    public async Task Test_ChatForwardingExecutor_ForwardsChatMessageUnmodifiedAsync()
    {
        // Arrange
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));
        ChatMessage testMessage = new(ChatRoleTestingExtensions.CustomChatRole, TestMessageContent);

        // Act
        TestWorkflowContext testContext = await this.RunForwardMessageTestAsync(executor, testMessage);

        // Assert
        Assert.Same(testMessage, Assert.Single(testContext.SentMessages));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_ChatForwardingExecutor_ForwardsChatMessageListUnmodifiedAsync(bool sendAsIEnumerable)
    {
        // Arrange
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));
        List<ChatMessage> testMessages = [new(ChatRoleTestingExtensions.CustomChatRole, TestMessageContent),
                                          new(ChatRole.Assistant, "ResponseMessage")];

        // Act
        TestWorkflowContext testContext
            = sendAsIEnumerable
            ? await this.RunForwardMessageTestAsync<IEnumerable<ChatMessage>>(executor, testMessages)
            : await this.RunForwardMessageTestAsync(executor, testMessages);

        // Assert
        Assert.Same(testMessages, Assert.Single(testContext.SentMessages));
    }

    [Fact]
    public async Task Test_ChatForwardingExecutor_ForwardsChatMessageArrayUnchangedAsync()
    {
        // Arrange
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));
        ChatMessage[] testMessages = [new(ChatRoleTestingExtensions.CustomChatRole, TestMessageContent),
                                      new(ChatRole.Assistant, "ResponseMessage")];

        // Act
        TestWorkflowContext testContext = await this.RunForwardMessageTestAsync(executor, testMessages);

        // Assert
        Assert.Same(testMessages, Assert.Single(testContext.SentMessages));
    }

    [Fact]
    public async Task Test_ChatForwardingExecutor_ForwardsMessageCollectionAsListAsync()
    {
        // Arrange
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));
        ConcurrentBag<ChatMessage> testMessages = [new(ChatRoleTestingExtensions.CustomChatRole, TestMessageContent),
                                                   new(ChatRole.Assistant, "ResponseMessage")];

        // Act
        TestWorkflowContext testContext = await this.RunForwardMessageTestAsync(executor, testMessages);

        // Assert
        IReadOnlyList<ChatMessage> forwardedMessages =
            Assert.IsAssignableFrom<IReadOnlyList<ChatMessage>>(Assert.Single(testContext.SentMessages, messages => !ReferenceEquals(messages, testMessages)));
        Assert.Equivalent(testMessages, forwardedMessages);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_ChatForwardingExecutor_ForwardsTurnTokenUnmodifiedAsync(bool? emitEvents)
    {
        // Arrange
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));
        TurnToken testTurnToken = new(emitEvents);

        // Act
        TestWorkflowContext testContext = await this.RunForwardMessageTestAsync(executor, testTurnToken);

        // Assert
        Assert.Equal(testTurnToken, Assert.Single(testContext.SentMessages));
    }
}
