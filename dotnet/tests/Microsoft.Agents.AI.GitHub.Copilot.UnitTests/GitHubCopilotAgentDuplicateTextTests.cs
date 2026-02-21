// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GitHub.Copilot.UnitTests;

/// <summary>
/// Tests that verify the fix for issue #3979 — GitHubCopilotAgent produces duplicated text content.
/// The bug was caused by both AssistantMessageDeltaEvent (incremental chunks) and
/// AssistantMessageEvent (complete assembled message) producing TextContent in
/// the streaming output. Consumers concatenating all update text would see the
/// content twice.
/// </summary>
public sealed class GitHubCopilotAgentDuplicateTextTests : IAsyncDisposable
{
    private readonly GitHubCopilotAgent _agent;

    public GitHubCopilotAgentDuplicateTextTests()
    {
        CopilotClient copilotClient = new(new CopilotClientOptions { AutoStart = false });
        _agent = new GitHubCopilotAgent(copilotClient, sessionConfig: null, ownsClient: false, id: "test-agent", name: "Test Agent", description: "Test agent");
    }

    public ValueTask DisposeAsync() => _agent.DisposeAsync();

    [Fact]
    public void ConvertDeltaEvent_ProducesTextContent()
    {
        // Arrange
        var deltaEvent = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData
            {
                DeltaContent = "Hello ",
                MessageId = "msg-1",
            },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(deltaEvent);

        // Assert — delta events MUST produce TextContent for streaming
        Assert.NotNull(update);
        Assert.Single(update.Contents);
        TextContent textContent = Assert.IsType<TextContent>(update.Contents[0]);
        Assert.Equal("Hello ", textContent.Text);
        Assert.Same(deltaEvent, textContent.RawRepresentation);
    }

    [Fact]
    public void ConvertDeltaEvent_PreservesMessageId()
    {
        // Arrange
        var deltaEvent = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData
            {
                DeltaContent = "test",
                MessageId = "msg-42",
            },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(deltaEvent);

        // Assert
        Assert.Equal("msg-42", update.MessageId);
        Assert.Equal("test-agent", update.AgentId);
        Assert.Equal(ChatRole.Assistant, update.Role);
    }

    [Fact]
    public void ConvertAssistantMessageEvent_DoesNotProduceTextContent()
    {
        // Arrange — AssistantMessageEvent contains the full assembled text
        var messageEvent = new AssistantMessageEvent
        {
            Data = new AssistantMessageData
            {
                Content = "Hello world! This is the complete message.",
                MessageId = "msg-1",
            },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(messageEvent);

        // Assert — must NOT produce TextContent to avoid duplicating delta text (#3979)
        Assert.NotNull(update);
        Assert.Single(update.Contents);
        Assert.IsNotType<TextContent>(update.Contents[0]);
        Assert.Same(messageEvent, update.Contents[0].RawRepresentation);
    }

    [Fact]
    public void ConvertAssistantMessageEvent_PreservesIdsAndTimestamp()
    {
        // Arrange
        var messageEvent = new AssistantMessageEvent
        {
            Data = new AssistantMessageData
            {
                Content = "complete text",
                MessageId = "msg-99",
            },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(messageEvent);

        // Assert — metadata is preserved even without TextContent
        Assert.Equal("msg-99", update.MessageId);
        Assert.Equal("msg-99", update.ResponseId);
        Assert.Equal("test-agent", update.AgentId);
        Assert.Equal(ChatRole.Assistant, update.Role);
    }

    [Fact]
    public void StreamingSimulation_DeltasPlusComplete_NoDuplicatedText()
    {
        // Arrange — simulate the event sequence: 3 deltas + 1 complete message
        const string Part1 = "Hello ";
        const string Part2 = "world";
        const string Part3 = "!";
        const string FullText = Part1 + Part2 + Part3;

        var delta1 = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData { DeltaContent = Part1, MessageId = "msg-1" },
        };
        var delta2 = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData { DeltaContent = Part2, MessageId = "msg-1" },
        };
        var delta3 = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData { DeltaContent = Part3, MessageId = "msg-1" },
        };
        var completeMessage = new AssistantMessageEvent
        {
            Data = new AssistantMessageData { Content = FullText, MessageId = "msg-1" },
        };

        // Act — convert all events (as would happen in the streaming pipeline)
        var updates = new List<AgentResponseUpdate>
        {
            _agent.ConvertToAgentResponseUpdate(delta1),
            _agent.ConvertToAgentResponseUpdate(delta2),
            _agent.ConvertToAgentResponseUpdate(delta3),
            _agent.ConvertToAgentResponseUpdate(completeMessage),
        };

        // Assert — collect all TextContent from all updates
        string collectedText = string.Concat(
            updates.SelectMany(u => u.Contents)
                   .OfType<TextContent>()
                   .Select(tc => tc.Text));

        // The collected text must equal the full text exactly once (no duplication)
        Assert.Equal(FullText, collectedText);
    }

    [Fact]
    public void ConvertDeltaEvent_EmptyDeltaContent_ProducesEmptyTextContent()
    {
        // Arrange — DeltaContent is empty string
        var deltaEvent = new AssistantMessageDeltaEvent
        {
            Data = new AssistantMessageDeltaData { DeltaContent = string.Empty, MessageId = "msg-empty" },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(deltaEvent);

        // Assert — empty delta produces empty TextContent (defensive behavior)
        TextContent textContent = Assert.IsType<TextContent>(update.Contents[0]);
        Assert.Equal(string.Empty, textContent.Text);
    }

    [Fact]
    public void ConvertUsageEvent_ProducesUsageContent_NotTextContent()
    {
        // Arrange
        var usageEvent = new AssistantUsageEvent
        {
            Data = new AssistantUsageData
            {
                Model = "gpt-4o",
                InputTokens = 10,
                OutputTokens = 25,
            },
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate(usageEvent);

        // Assert — usage events should produce UsageContent, not TextContent
        Assert.Single(update.Contents);
        UsageContent usageContent = Assert.IsType<UsageContent>(update.Contents[0]);
        Assert.Equal(10, usageContent.Details.InputTokenCount);
        Assert.Equal(25, usageContent.Details.OutputTokenCount);
        Assert.Equal(35, usageContent.Details.TotalTokenCount);
    }

    [Fact]
    public void ConvertSessionEvent_ProducesRawContent_NotTextContent()
    {
        // Arrange — generic session event (falls to default handler)
        var sessionEvent = new SessionIdleEvent
        {
            Data = new SessionIdleData(),
        };

        // Act
        AgentResponseUpdate update = _agent.ConvertToAgentResponseUpdate((SessionEvent)sessionEvent);

        // Assert
        Assert.Single(update.Contents);
        Assert.IsNotType<TextContent>(update.Contents[0]);
        Assert.Same(sessionEvent, update.Contents[0].RawRepresentation);
    }
}
