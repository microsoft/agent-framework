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
    public void Test_MessageMerger_PreservesFunctionCallOrderingWhenToolResultHasCreatedAt()
    {
        // Arrange
        string responseId = Guid.NewGuid().ToString("N");
        string functionCallMessageId = Guid.NewGuid().ToString("N");
        string functionResultMessageId = Guid.NewGuid().ToString("N");
        string callId = Guid.NewGuid().ToString("N");
        DateTimeOffset toolResultCreatedAt = DateTimeOffset.UtcNow;

        MessageMerger merger = new();

        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = functionCallMessageId,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new FunctionCallContent(callId, "handoff_to_TestAgent2")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = functionResultMessageId,
            AgentId = TestAgentId1,
            CreatedAt = toolResultCreatedAt,
            Role = ChatRole.Tool,
            Contents = [new FunctionResultContent(callId, "Transferred.")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert
        response.Messages.Should().HaveCount(2);
        response.Messages[0].Role.Should().Be(ChatRole.Assistant);
        response.Messages[0].Contents.Should().ContainSingle().Which.Should().BeOfType<FunctionCallContent>();
        response.Messages[1].Role.Should().Be(ChatRole.Tool);
        response.Messages[1].Contents.Should().ContainSingle().Which.Should().BeOfType<FunctionResultContent>();
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

    #region Invariant 2: Output Order Preservation Tests

    [Fact]
    public void Test_MessageMerger_PreservesInsertionOrder_WhenNoTimestamps()
    {
        // Arrange: Multiple updates without CreatedAt, in specific order A, B, C
        string responseId = Guid.NewGuid().ToString("N");
        string messageIdA = Guid.NewGuid().ToString("N");
        string messageIdB = Guid.NewGuid().ToString("N");
        string messageIdC = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        // Add updates without CreatedAt in order A, B, C
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdA,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Message A")],
            // No CreatedAt
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdB,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Message B")],
            // No CreatedAt
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdC,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Message C")],
            // No CreatedAt
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert: Output order should be A, B, C (insertion order)
        response.Messages.Should().HaveCount(3);
        response.Messages[0].Text.Should().Be("Message A");
        response.Messages[1].Text.Should().Be("Message B");
        response.Messages[2].Text.Should().Be("Message C");
    }

    [Fact]
    public void Test_MessageMerger_PreservesInsertionOrder_WhenMixedTimestamps()
    {
        // Arrange: Updates where some have CreatedAt and some don't
        string responseId = Guid.NewGuid().ToString("N");
        string messageIdA = Guid.NewGuid().ToString("N");
        string messageIdB = Guid.NewGuid().ToString("N");
        string messageIdC = Guid.NewGuid().ToString("N");

        DateTimeOffset time1 = DateTimeOffset.UtcNow.AddMinutes(-2);
        DateTimeOffset time3 = DateTimeOffset.UtcNow;

        MessageMerger merger = new();

        // A has timestamp (time1), B has no timestamp, C has timestamp (time3)
        // Insertion order: A, B, C
        // B should maintain its relative position among untimestamped messages
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdA,
            Role = ChatRole.Assistant,
            CreatedAt = time1,
            Contents = [new TextContent("Message A")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdB,
            Role = ChatRole.Assistant,
            // No CreatedAt - should use insertion order as tiebreaker
            Contents = [new TextContent("Message B")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdC,
            Role = ChatRole.Assistant,
            CreatedAt = time3,
            Contents = [new TextContent("Message C")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseId);

        // Assert: Untimestamped messages should maintain relative order via insertion index fallback
        response.Messages.Should().HaveCount(3);

        // A (time1) should come first, B (no timestamp, uses index 1) should be in middle,
        // C (time3) should come last since it has the latest timestamp
        response.Messages[0].Text.Should().Be("Message A");
        response.Messages[1].Text.Should().Be("Message B");
        response.Messages[2].Text.Should().Be("Message C");
    }

    [Fact]
    public void Test_MessageMerger_ReproducibleOrdering_WithMixedTimestamps()
    {
        // Arrange: 3+ messages with mixed null/non-null CreatedAt values
        // This tests that the same input sequence produces the same output
        // (run-to-run reproducibility for a fixed input)
        string responseId = Guid.NewGuid().ToString("N");
        string messageIdA = Guid.NewGuid().ToString("N");
        string messageIdB = Guid.NewGuid().ToString("N");
        string messageIdC = Guid.NewGuid().ToString("N");

        DateTimeOffset time10 = DateTimeOffset.UtcNow.AddSeconds(10);
        DateTimeOffset time5 = DateTimeOffset.UtcNow.AddSeconds(5);

        MessageMerger merger = new();

        // A: CreatedAt = time10, idx=0
        // B: CreatedAt = null, idx=1
        // C: CreatedAt = time5, idx=2
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdA,
            Role = ChatRole.Assistant,
            CreatedAt = time10,
            Contents = [new TextContent("Message A (T=10)")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdB,
            Role = ChatRole.Assistant,
            // No CreatedAt
            Contents = [new TextContent("Message B (no timestamp)")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdC,
            Role = ChatRole.Assistant,
            CreatedAt = time5,
            Contents = [new TextContent("Message C (T=5)")],
        });

        // Act - Run multiple times to verify reproducibility
        AgentResponse response1 = merger.ComputeMerged(responseId);

        // Create a fresh merger with same data to verify reproducibility
        MessageMerger merger2 = new();
        merger2.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdA,
            Role = ChatRole.Assistant,
            CreatedAt = time10,
            Contents = [new TextContent("Message A (T=10)")],
        });
        merger2.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdB,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Message B (no timestamp)")],
        });
        merger2.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseId,
            MessageId = messageIdC,
            Role = ChatRole.Assistant,
            CreatedAt = time5,
            Contents = [new TextContent("Message C (T=5)")],
        });
        AgentResponse response2 = merger2.ComputeMerged(responseId);

        // Assert: Result is reproducible and consistent across runs with same input order
        response1.Messages.Should().HaveCount(3);
        response2.Messages.Should().HaveCount(3);

        // Both runs should produce identical ordering
        for (int i = 0; i < 3; i++)
        {
            response1.Messages[i].Text.Should().Be(response2.Messages[i].Text);
        }
    }

    #endregion

    #region Invariant 3: Agent Message Grouping Tests

    [Fact]
    public void Test_MessageMerger_GroupsMessagesByResponseId_InMultiAgentScenario()
    {
        // Arrange: Interleaved updates from Agent1 (R1) and Agent2 (R2)
        string responseIdR1 = Guid.NewGuid().ToString("N");
        string responseIdR2 = Guid.NewGuid().ToString("N");
        string messageIdA1M1 = Guid.NewGuid().ToString("N");
        string messageIdA1M2 = Guid.NewGuid().ToString("N");
        string messageIdA2M1 = Guid.NewGuid().ToString("N");
        string messageIdA2M2 = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        // Interleaved arrival: A1-msg1, A2-msg1, A1-msg2, A2-msg2
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR1,
            MessageId = messageIdA1M1,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent1 Message 1")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR2,
            MessageId = messageIdA2M1,
            AgentId = TestAgentId2,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent2 Message 1")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR1,
            MessageId = messageIdA1M2,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent1 Message 2")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR2,
            MessageId = messageIdA2M2,
            AgentId = TestAgentId2,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent2 Message 2")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseIdR1);

        // Assert: Messages should be grouped by ResponseId (which groups by agent)
        // Output should be either [A1-msg1, A1-msg2, A2-msg1, A2-msg2] or [A2-msg1, A2-msg2, A1-msg1, A1-msg2]
        // The key invariant: Agent1's messages are contiguous, Agent2's messages are contiguous
        response.Messages.Should().HaveCount(4);

        // Verify grouping - collect message texts and verify they're grouped by agent
        var messageTexts = response.Messages.Select(m => m.Text).ToList();

        // Find first Agent1 message index and first Agent2 message index
        int firstA1Index = messageTexts.FindIndex(t => t.StartsWith("Agent1", StringComparison.Ordinal));
        int firstA2Index = messageTexts.FindIndex(t => t.StartsWith("Agent2", StringComparison.Ordinal));

        // Assert both indices are valid (messages were found)
        firstA1Index.Should().BeGreaterThanOrEqualTo(0, "Agent1 messages should be present in response");
        firstA2Index.Should().BeGreaterThanOrEqualTo(0, "Agent2 messages should be present in response");

        // All Agent1 messages should be contiguous (either at start or after all Agent2 messages)
        var a1Messages = messageTexts.Where(t => t.StartsWith("Agent1", StringComparison.Ordinal)).ToList();
        var a2Messages = messageTexts.Where(t => t.StartsWith("Agent2", StringComparison.Ordinal)).ToList();

        a1Messages.Should().HaveCount(2);
        a2Messages.Should().HaveCount(2);

        // Verify no interleaving: if A1 comes first, A2 should come after all A1 messages
        if (firstA1Index < firstA2Index)
        {
            // A1 messages at indices 0, 1 and A2 messages at indices 2, 3
            messageTexts[0].Should().StartWith("Agent1");
            messageTexts[1].Should().StartWith("Agent1");
            messageTexts[2].Should().StartWith("Agent2");
            messageTexts[3].Should().StartWith("Agent2");
        }
        else
        {
            // A2 messages at indices 0, 1 and A1 messages at indices 2, 3
            messageTexts[0].Should().StartWith("Agent2");
            messageTexts[1].Should().StartWith("Agent2");
            messageTexts[2].Should().StartWith("Agent1");
            messageTexts[3].Should().StartWith("Agent1");
        }
    }

    [Fact]
    public void Test_MessageMerger_MaintainsAgentGrouping_WithDifferentResponseIds()
    {
        // Arrange: Agent1 uses ResponseId=R1, Agent2 uses ResponseId=R2
        // Multiple messages per ResponseId to properly test contiguity
        string responseIdR1 = Guid.NewGuid().ToString("N");
        string responseIdR2 = Guid.NewGuid().ToString("N");
        string messageIdA1M1 = Guid.NewGuid().ToString("N");
        string messageIdA1M2 = Guid.NewGuid().ToString("N");
        string messageIdA1M3 = Guid.NewGuid().ToString("N");
        string messageIdA2M1 = Guid.NewGuid().ToString("N");
        string messageIdA2M2 = Guid.NewGuid().ToString("N");
        string messageIdA2M3 = Guid.NewGuid().ToString("N");

        MessageMerger merger = new();

        // Interleaved arrival: A1-1, A2-1, A1-2, A2-2, A1-3, A2-3
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR1,
            MessageId = messageIdA1M1,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent1 Response 1")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR2,
            MessageId = messageIdA2M1,
            AgentId = TestAgentId2,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent2 Response 1")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR1,
            MessageId = messageIdA1M2,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent1 Response 2")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR2,
            MessageId = messageIdA2M2,
            AgentId = TestAgentId2,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent2 Response 2")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR1,
            MessageId = messageIdA1M3,
            AgentId = TestAgentId1,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent1 Response 3")],
        });
        merger.AddUpdate(new AgentResponseUpdate
        {
            ResponseId = responseIdR2,
            MessageId = messageIdA2M3,
            AgentId = TestAgentId2,
            Role = ChatRole.Assistant,
            Contents = [new TextContent("Agent2 Response 3")],
        });

        // Act
        AgentResponse response = merger.ComputeMerged(responseIdR1);

        // Assert: Messages from each agent are contiguous (not interleaved)
        response.Messages.Should().HaveCount(6);

        var messageTexts = response.Messages.Select(m => m.Text).ToList();

        // Verify all messages are present
        messageTexts.Should().Contain("Agent1 Response 1");
        messageTexts.Should().Contain("Agent1 Response 2");
        messageTexts.Should().Contain("Agent1 Response 3");
        messageTexts.Should().Contain("Agent2 Response 1");
        messageTexts.Should().Contain("Agent2 Response 2");
        messageTexts.Should().Contain("Agent2 Response 3");

        // Find indices to verify contiguity
        int firstA1Index = messageTexts.FindIndex(t => t.StartsWith("Agent1", StringComparison.Ordinal));
        int lastA1Index = messageTexts.FindLastIndex(t => t.StartsWith("Agent1", StringComparison.Ordinal));
        int firstA2Index = messageTexts.FindIndex(t => t.StartsWith("Agent2", StringComparison.Ordinal));
        int lastA2Index = messageTexts.FindLastIndex(t => t.StartsWith("Agent2", StringComparison.Ordinal));

        // Assert indices are valid
        firstA1Index.Should().BeGreaterThanOrEqualTo(0, "Agent1 messages should be present");
        firstA2Index.Should().BeGreaterThanOrEqualTo(0, "Agent2 messages should be present");

        // Verify contiguity: all Agent1 messages should span exactly 3 consecutive indices
        (lastA1Index - firstA1Index).Should().Be(2, "Agent1 messages should be contiguous (3 messages spanning 2 index gaps)");
        (lastA2Index - firstA2Index).Should().Be(2, "Agent2 messages should be contiguous (3 messages spanning 2 index gaps)");

        // Verify no interleaving: ranges should not overlap
        bool a1BeforeA2 = lastA1Index < firstA2Index;
        bool a2BeforeA1 = lastA2Index < firstA1Index;
        (a1BeforeA2 || a2BeforeA1).Should().BeTrue("Agent message blocks should not interleave");
    }

    #endregion
}
