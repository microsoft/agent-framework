// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public abstract class AIAgentHostingExecutorTestsBase
{
    protected const string TestAgentId = nameof(TestAgentId);
    protected const string TestAgentName = nameof(TestAgentName);

    private static readonly string[] s_messageStrings = [
        "",
        "Hello world!",
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "Quisque dignissim ante odio, at facilisis orci porta a. Duis mi augue, fringilla eu egestas a, pellentesque sed lacus."
    ];

    protected static List<ChatMessage> TestMessages => TestReplayAgent.ToChatMessages(s_messageStrings);

    protected static void CheckResponseUpdateEventsAgainstTestMessages(AgentResponseUpdateEvent[] updates, bool expectingEvents, string expectedExecutorId)
    {
        if (expectingEvents)
        {
            // The way TestReplayAgent is set up, it will emit one update per non-empty AIContent
            List<AIContent> expectedUpdateContents = TestMessages.SelectMany(message => message.Contents).ToList();

            updates.Should().HaveCount(expectedUpdateContents.Count);
            for (int i = 0; i < updates.Length; i++)
            {
                AgentResponseUpdateEvent updateEvent = updates[i];
                AIContent expectedUpdateContent = expectedUpdateContents[i];

                updateEvent.ExecutorId.Should().Be(expectedExecutorId);

                AgentResponseUpdate update = updateEvent.Update;
                update.AuthorName.Should().Be(TestAgentName);
                update.AgentId.Should().Be(TestAgentId);
                update.Contents.Should().HaveCount(1);
                update.Contents[0].Should().BeEquivalentTo(expectedUpdateContent);
            }
        }
        else
        {
            updates.Should().BeEmpty();
        }
    }

    protected static void CheckResponseEventsAgainstTestMessages(AgentResponseEvent[] updates, bool expectingResponse, string expectedExecutorId)
    {
        if (expectingResponse)
        {
            updates.Should().HaveCount(1);

            AgentResponseEvent responseEvent = updates[0];
            responseEvent.ExecutorId.Should().Be(expectedExecutorId);

            AgentResponse response = responseEvent.Response;
            response.AgentId.Should().Be(TestAgentId);
            response.Messages.Should().HaveCount(TestMessages.Count - 1);

            for (int i = 0; i < response.Messages.Count; i++)
            {
                ChatMessage responseMessage = response.Messages[i];
                ChatMessage expectedMessage = TestMessages[i + 1]; // Skip the first empty message

                responseMessage.AuthorName.Should().Be(TestAgentName);
                responseMessage.Text.Should().Be(expectedMessage.Text);
            }
        }
        else
        {
            updates.Should().BeEmpty();
        }
    }
}
