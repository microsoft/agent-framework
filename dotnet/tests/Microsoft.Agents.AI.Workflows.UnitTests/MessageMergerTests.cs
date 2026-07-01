// Copyright (c) Microsoft. All rights reserved.

using System;
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
    public void Test_MessageMerger_PreservesMessageOrderWhenReasoningLacksCreatedAt()
    {
        // Arrange: a reasoning model streams its reasoning summary first (without a CreatedAt
        // timestamp) followed by the textual answer (with one). Both share a response id and carry
        // distinct, explicit message ids, so they are legitimately two messages. This guards against
        // ordering by CreatedAt, which would otherwise push the timestamp-less reasoning message
        // after the text message.
        string responseId = Guid.NewGuid().ToString("N");
        string reasoningMessageId = Guid.NewGuid().ToString("N");
        string textMessageId = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = reasoningMessageId,
            Contents = [new TextReasoningContent("Thinking about the question")],
            CreatedAt = null,
        });

        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = textMessageId,
            Contents = [new TextContent("Here is the answer.")],
            CreatedAt = DateTimeOffset.UtcNow,
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert - the reasoning message must remain first, matching a directly-invoked agent.
        response.Messages.Should().HaveCount(2);

        response.Messages[0].Contents.Should().ContainSingle()
            .Which.Should().BeOfType<TextReasoningContent>()
            .Which.Text.Should().Be("Thinking about the question");

        response.Messages[1].Contents.Should().ContainSingle()
            .Which.Should().BeOfType<TextContent>()
            .Which.Text.Should().Be("Here is the answer.");
    }

    [Fact]
    public void Test_MessageMerger_MergesReasoningAndTextIntoSingleMessageWhenReasoningLacksMessageId()
    {
        // Arrange: this mirrors the exact streaming shape captured from the workflow-as-agent repro
        // in https://github.com/microsoft/agent-framework/issues/6329. A reasoning model (e.g. Azure
        // OpenAI Responses) streams its reasoning summary first as several id-less updates (the
        // Responses API emits reasoning updates with a null MessageId and no CreatedAt), followed by
        // the textual answer carrying a real message id. All updates share the same response id.
        //
        // Previously the merger bucketed updates per MessageId and appended the id-less reasoning
        // updates last, splitting one assistant message into two ([text], [reasoning]) in reversed
        // order. Grouping is now delegated to M.E.AI, which keeps the reasoning in the same message
        // as the text that follows it - exactly as a directly-invoked agent produces.
        string responseId = "resp_" + Guid.NewGuid().ToString("N");
        string textMessageId = "msg_" + Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        // Reasoning summary: id-less updates without a CreatedAt timestamp.
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = null,
            Contents = [new TextReasoningContent("Thinking ")],
            CreatedAt = null,
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = null,
            Contents = [new TextReasoningContent("about the question")],
            CreatedAt = null,
        });

        // Final answer: text updates carrying a real message id.
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = textMessageId,
            Contents = [new TextContent("Here is ")],
            CreatedAt = DateTimeOffset.UtcNow,
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            MessageId = textMessageId,
            Contents = [new TextContent("the answer.")],
            CreatedAt = DateTimeOffset.UtcNow,
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert - a single assistant message with reasoning first, then the answer text.
        response.Messages.Should().ContainSingle();

        ChatMessage message = response.Messages[0];
        message.Role.Should().Be(ChatRole.Assistant);
        message.Contents.Should().HaveCount(2);

        message.Contents[0].Should().BeOfType<TextReasoningContent>()
            .Which.Text.Should().Be("Thinking about the question");

        message.Contents[1].Should().BeOfType<TextContent>()
            .Which.Text.Should().Be("Here is the answer.");
    }
}
