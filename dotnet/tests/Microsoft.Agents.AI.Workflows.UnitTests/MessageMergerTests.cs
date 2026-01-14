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
        DateTimeOffset creationTime = DateTimeOffset.UtcNow;
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
        response.CreatedAt.Should().NotBe(creationTime);
        response.Messages[0].CreatedAt.Should().Be(creationTime);
        response.Messages[0].Contents.Should().HaveCount(1);
    }
}
