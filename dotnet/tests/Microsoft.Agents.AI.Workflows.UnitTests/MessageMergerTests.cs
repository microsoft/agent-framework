// Copyright (c) Microsoft. All rights reserved.

using System;
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

        ChatMessage message = Assert.Single(response.Messages);
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal(TestAuthorName1, message.AuthorName);
        Assert.Equal(TestAgentId1, response.AgentId);
        Assert.NotNull(response.CreatedAt);
        Assert.True(response.CreatedAt.Value >= creationTime);
        Assert.True(response.CreatedAt.Value >= (creationTime - TimeSpan.FromSeconds(5)) && response.CreatedAt.Value <= (creationTime + TimeSpan.FromSeconds(5)));
        Assert.Equal(creationTime, message.CreatedAt);
        Assert.Single(message.Contents);
        Assert.Null(response.FinishReason);
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
        Assert.Equal(ChatFinishReason.ContentFilter, response.FinishReason);
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
        Assert.Collection(
            response.Messages,
            message => Assert.Equal("first", message.Text),
            message => Assert.Equal("second", message.Text),
            message => Assert.Equal("third", message.Text),
            message => Assert.Equal("fourth", message.Text));
        Assert.Equal(now.AddMinutes(1), response.Messages[0].CreatedAt);
        Assert.Equal(now.AddMinutes(-1), response.Messages[2].CreatedAt);
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
        Assert.Equal("A1", response.Messages[0].Text);
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
        Assert.Equal(2, response.Messages.Count);
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
        Assert.Equal(3, response.Messages.Count);
        Assert.Equal("before", response.Messages[0].Text);
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
        Assert.Equal("AB", response.Messages[0].Text);
    }

    [Fact]
    public void Test_MessageMerger_FoldsIdentifierlessReasoningIntoFollowingMessage()
    {
        // Arrange - a streamed reasoning summary arrives without a message id, immediately
        // followed by the actual answer that carries a message id (same assistant role).
        // See https://github.com/microsoft/agent-framework/issues/6329.
        const string ResponseId = "response";
        const string MessageId = "msg_answer";
        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            Role = ChatRole.Assistant,
            Contents = [new TextReasoningContent("thinking about the question")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            MessageId = MessageId,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("The reformulated question.")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId);

        // Assert - reasoning and answer should be folded into a single message with two contents,
        // adopting the following message's id.
        ChatMessage mergedMessage = Assert.Single(response.Messages);
        Assert.Equal(ChatRole.Assistant, mergedMessage.Role);
        Assert.Equal(MessageId, mergedMessage.MessageId);
        Assert.Equal(2, mergedMessage.Contents.Count);
        Assert.Equal("thinking about the question", Assert.IsType<TextReasoningContent>(mergedMessage.Contents[0]).Text);
        Assert.Equal("The reformulated question.", Assert.IsType<TextContent>(mergedMessage.Contents[1]).Text);
        Assert.Equal("The reformulated question.", mergedMessage.Text);
    }

    [Fact]
    public void Test_MessageMerger_DoesNotFoldIdentifierlessReasoningIntoDifferentRole()
    {
        // Arrange - an id-less segment is only folded when the following message shares its role.
        const string ResponseId = "response";
        const string MessageId = "msg_tool";
        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            Role = ChatRole.Assistant,
            Contents = [new TextReasoningContent("thinking")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = ResponseId,
            MessageId = MessageId,
            Role = ChatRole.Tool,
            Contents = [new FunctionResultContent("call", "done")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId);

        // Assert - different roles must remain separate messages.
        Assert.Equal(2, response.Messages.Count);
        Assert.Equal(ChatRole.Assistant, response.Messages[0].Role);
        Assert.IsType<TextReasoningContent>(Assert.Single(response.Messages[0].Contents));
        Assert.Equal(ChatRole.Tool, response.Messages[1].Role);
    }

    /// <summary>
    /// Verify that usage from merged response buckets is aggregated with distinct token values and additional counts.
    /// </summary>
    [Fact]
    public void Test_MessageMerger_AggregatesUsageAndAdditionalCounts()
    {
        // Arrange
        const string ResponseId1 = "response-1";
        const string ResponseId2 = "response-2";
        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant, "first")
        {
            ResponseId = ResponseId1,
            MessageId = "message-1",
        });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant,
            [new UsageContent(new UsageDetails
            {
                InputTokenCount = 2,
                OutputTokenCount = 3,
                TotalTokenCount = 5,
                AdditionalCounts = new() { ["cached"] = 7, ["reasoning"] = 11 },
            })])
        {
            ResponseId = ResponseId1,
            MessageId = "message-1",
        });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant, "second")
        {
            ResponseId = ResponseId2,
            MessageId = "message-2",
        });
        merger.AddUpdate(new AgentResponseUpdate(ChatRole.Assistant,
            [new UsageContent(new UsageDetails
            {
                InputTokenCount = 29,
                OutputTokenCount = 7,
                TotalTokenCount = 36,
                AdditionalCounts = new() { ["cached"] = 13, ["audio"] = 17 },
            })])
        {
            ResponseId = ResponseId2,
            MessageId = "message-2",
        });

        // Act
        AgentResponse response = merger.ComputeMerged(ResponseId1);

        // Assert
        Assert.NotNull(response.Usage);
        Assert.Equal(31, response.Usage!.InputTokenCount);
        Assert.Equal(10, response.Usage.OutputTokenCount);
        Assert.Equal(41, response.Usage.TotalTokenCount);
        Assert.NotNull(response.Usage.AdditionalCounts);
        Assert.Equal(20, response.Usage.AdditionalCounts!["cached"]);
        Assert.Equal(11, response.Usage.AdditionalCounts["reasoning"]);
        Assert.Equal(17, response.Usage.AdditionalCounts["audio"]);
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
        Assert.Equal(2, response.Messages.Count);

        Assert.Equal("Thinking about the question", Assert.IsType<TextReasoningContent>(Assert.Single(response.Messages[0].Contents)).Text);

        Assert.Equal("Here is the answer.", Assert.IsType<TextContent>(Assert.Single(response.Messages[1].Contents)).Text);
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
        // order. Now M.E.AI (using ToAgentResponse) only groups contiguous updates sharing a MessageId,
        // while the explicit fold loop in ComputeMerged folds the id-less reasoning into the id'd
        // text message that follows it - keeping them in a single assistant message, exactly as a
        // directly-invoked agent produces.
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
        Assert.Single(response.Messages);

        ChatMessage message = response.Messages[0];
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal(2, message.Contents.Count);

        Assert.Equal("Thinking about the question", Assert.IsType<TextReasoningContent>(message.Contents[0]).Text);

        Assert.Equal("Here is the answer.", Assert.IsType<TextContent>(message.Contents[1]).Text);
    }

    [Fact]
    public void Test_MessageMerger_FoldsIdentifierlessReasoningIntoFollowingMessageAcrossResponseBuckets()
    {
        // Arrange: this reproduces the workflow-as-agent repro where a reasoning summary and the
        // answer text end up in DIFFERENT response buckets (distinct response ids). The per-response
        // fold cannot merge across buckets, so this exercises the flattened-message fold in the outer
        // ComputeMerged. See https://github.com/microsoft/agent-framework/issues/6329.
        const string ReasoningResponseId = "resp_reasoning";
        const string TextResponseId = "resp_text";
        const string TextMessageId = "msg_answer";

        MessageMerger merger = new();

        // Reasoning summary: id-less update in its own response bucket, seen first.
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = ReasoningResponseId,
            MessageId = null,
            Contents = [new TextReasoningContent("thinking about the question")],
        });

        // Final answer: text update carrying a real message id in a different response bucket.
        merger.AddUpdate(new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            ResponseId = TextResponseId,
            MessageId = TextMessageId,
            Contents = [new TextContent("The reformulated question.")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(TextResponseId);

        // Assert - a single assistant message adopting the answer's id, reasoning first then text.
        Assert.Single(response.Messages);
        ChatMessage message = response.Messages[0];
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal(TextMessageId, message.MessageId);
        Assert.Equal(2, message.Contents.Count);
        Assert.Equal("thinking about the question", Assert.IsType<TextReasoningContent>(message.Contents[0]).Text);
        Assert.Equal("The reformulated question.", Assert.IsType<TextContent>(message.Contents[1]).Text);
        Assert.Equal("The reformulated question.", message.Text);
    }
}
