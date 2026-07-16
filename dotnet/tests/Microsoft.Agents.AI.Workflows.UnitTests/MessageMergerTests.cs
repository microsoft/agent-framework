// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MessageMergerTests
{
    public static string TestAgentId1 => "TestAgent1";
    public static string TestAgentId2 => "TestAgent2";

    public static string TestAuthorName1 => "Assistant1";
    public static string TestAuthorName2 => "Assistant2";

    [Fact]
    public void Test_MessageMerger_AssemblesMessage()
    {
        DateTimeOffset creationTime = DateTimeOffset.UtcNow.Subtract(TimeSpan.FromSeconds(1));
        string responseId = Guid.NewGuid().ToString("N");
        string messageId = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        foreach (AgentResponseUpdate update in "Hello Agent Framework Workflows!".ToAgentRunStream(authorName: TestAuthorName1, agentId: TestAgentId1, messageId: messageId, createdAt: creationTime, responseId: responseId))
        {
            merger.AddUpdate(update);
        }

        AgentResponse response = merger.ComputeMerged(responseId);

        response.Messages.Should().HaveCount(1);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].AuthorName.Should().Be(TestAuthorName1);
        response.AgentId.Should().Be(TestAgentId1);
        response.CreatedAt.Should().HaveValue();
        response.CreatedAt.Value.Should().BeOnOrAfter(creationTime);
        response.CreatedAt.Value.Should().BeCloseTo(creationTime, precision: TimeSpan.FromSeconds(5));
        response.Messages[0].CreatedAt.Should().Be(creationTime);
        response.Messages[0].Contents.Should().HaveCount(1);
        response.FinishReason.Should().BeNull();
    }

    [Fact]
    public void Test_MessageMerger_PropagatesFinishReasonFromUpdates()
    {
        // Arrange
        string responseId = Guid.NewGuid().ToString("N");
        string messageId = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        foreach (AgentResponseUpdate update in "Hello".ToAgentRunStream(agentId: TestAgentId1, messageId: messageId, responseId: responseId))
        {
            merger.AddUpdate(update);
        }

        // Add a final update with FinishReason set
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageId,
            FinishReason = ChatFinishReason.ContentFilter,
            Role = ChatRole.Assistant,
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert - FinishReason from the update should propagate through
        response.FinishReason.Should().Be(ChatFinishReason.ContentFilter);
    }

    [Fact]
    public void Test_MessageMerger_PreservesFirstSeenMessageOrder()
    {
        // Arrange
        string responseId = Guid.NewGuid().ToString("N");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        MessageMerger merger = new();

        AddTextMessage(merger, responseId, "first", now.AddMinutes(1));
        AddTextMessage(merger, responseId, "second", null);
        AddTextMessage(merger, responseId, "third", now.AddMinutes(-1));
        AddTextMessage(merger, responseId, "fourth", now.AddMinutes(-1));

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert
        response.Messages.Select(message => message.Text).Should().Equal("first", "second", "third", "fourth");
        response.Messages[0].CreatedAt.Should().Be(now.AddMinutes(1));
        response.Messages[2].CreatedAt.Should().Be(now.AddMinutes(-1));
    }

    [Fact]
    public void Test_MessageMerger_KeepsResponsesContiguousInFirstSeenOrder()
    {
        // Arrange
        const string ResponseId1 = "response-1";
        const string ResponseId2 = "response-2";
        MessageMerger merger = new();

        AddTextMessage(merger, ResponseId1, "A1");
        AddTextMessage(merger, ResponseId2, "B1");
        AddTextMessage(merger, ResponseId1, "A2");
        AddTextMessage(merger, ResponseId2, "B2");

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId1);

        // Assert
        response.Messages.Select(message => message.Text).Should().Equal("A1", "A2", "B1", "B2");
    }

    [Fact]
    public void Test_MessageMerger_PreservesFunctionCallResultOrder()
    {
        // Arrange
        const string ResponseId = "response";
        const string CallId = "call";
        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            MessageId = "call-message",
            Role = ChatRole.Assistant,
            Contents = [new FunctionCallContent(CallId, "handoff")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            MessageId = "result-message",
            Role = ChatRole.Tool,
            CreatedAt = DateTimeOffset.UtcNow,
            Contents = [new FunctionResultContent(CallId, "Transferred.")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId);

        // Assert
        response.Messages.Should().HaveCount(2);
        Assert.Equal(CallId, Assert.IsType<FunctionCallContent>(Assert.Single(response.Messages[0].Contents)).CallId);
        Assert.Equal(CallId, Assert.IsType<FunctionResultContent>(Assert.Single(response.Messages[1].Contents)).CallId);
    }

    [Fact]
    public void Test_MessageMerger_PreservesIdentifierlessMessageOrder()
    {
        // Arrange
        const string ResponseId = "response";
        const string CallId = "call";
        MessageMerger merger = new();

        AddTextMessage(merger, ResponseId, "before");
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            Role = ChatRole.Assistant,
            Contents = [new FunctionCallContent(CallId, "handoff")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            MessageId = "result-message",
            Role = ChatRole.Tool,
            CreatedAt = DateTimeOffset.UtcNow,
            Contents = [new FunctionResultContent(CallId, "Transferred.")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId);

        // Assert
        response.Messages.Should().HaveCount(3);
        response.Messages[0].Text.Should().Be("before");
        Assert.IsType<FunctionCallContent>(Assert.Single(response.Messages[1].Contents));
        Assert.IsType<FunctionResultContent>(Assert.Single(response.Messages[2].Contents));
    }

    [Fact]
    public void Test_MessageMerger_SeparatesIdentifierlessSegments()
    {
        // Arrange
        const string ResponseId = "response";
        const string MessageId = "message";
        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant, "A") { ResponseId = ResponseId, MessageId = MessageId });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Tool, "X") { ResponseId = ResponseId });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant, "B") { ResponseId = ResponseId, MessageId = MessageId });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Tool, "Y") { ResponseId = ResponseId });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId);

        // Assert
        response.Messages.Select(message => message.Text).Should().Equal("AB", "X", "Y");
    }

    private static void AddTextMessage(MessageMerger merger, string responseId, string text, DateTimeOffset? createdAt = null)
    {
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = Guid.NewGuid().ToString("N"),
            Role = ChatRole.Assistant,
            CreatedAt = createdAt,
            Contents = [new TextContent(text)],
        });
    }
}
