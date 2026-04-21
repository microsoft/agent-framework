// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
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

        callResult.Should().BeNull(); // ChatForwardingExecutor's do not have a return type

        return testContext;
    }

    private const string TestMessageContent = nameof(TestMessageContent);

    [Fact]
    public async Task Test_ChatForwardingExecutor_DoesNotForwardStringByDefaultAsync()
    {
        ChatForwardingExecutor executor = new(nameof(ChatForwardingExecutor));

        // Act
        Func<Task<TestWorkflowContext>> action = () => this.RunForwardMessageTestAsync(executor, TestMessageContent);
        await action.Should().ThrowAsync<NotSupportedException>();
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
        Func<Task<TestWorkflowContext>> action = () => this.RunForwardMessageTestAsync(executor, TestMessageContent);

        // Assert
        if (options.StringMessageChatRole is ChatRole chatRole)
        {
            TestWorkflowContext testContext = await action();

            testContext.SentMessages.Should().HaveCount(1)
                                .And.BeEquivalentTo([new ChatMessage(chatRole, TestMessageContent)]);
        }
        else
        {
            await action.Should().ThrowAsync<NotSupportedException>();
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
        testContext.SentMessages.Should().ContainSingle(message => ReferenceEquals(message, testMessage));
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
        testContext.SentMessages.Should().ContainSingle(messages => ReferenceEquals(messages, testMessages));
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
        testContext.SentMessages.Should().ContainSingle(messages => ReferenceEquals(messages, testMessages));
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
        testContext.SentMessages.Should().ContainSingle(messages => !ReferenceEquals(messages, testMessages))
                                     .And.Subject.Single().Should().BeEquivalentTo(testMessages);
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
        testContext.SentMessages.Should().BeEquivalentTo([testTurnToken]);
    }
}
