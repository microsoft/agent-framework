// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.WorkflowSequential;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class SequentialWorkflowTests
{
    [Fact]
    public async Task ClientReceivesOrderedExecutorStepsAndTextAsync()
    {
        // Arrange
        AIAgent writer = new DeterministicAgent("Writer", "draft");
        AIAgent reviewer = new DeterministicAgent("Reviewer", "final");
        Workflow workflow = SequentialWorkflow.Create(writer, reviewer);
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(
            workflow.AsAIAgent(name: "SequentialWorkflow"));
        AGUIChatClient chatClient = new(new(host.Client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(name: "client");
        AgentSession session = await clientAgent.CreateSessionAsync();

        // Act
        List<AgentResponseUpdate> updates = await clientAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"), session)
            .ToListAsync();

        // Assert
        string[] started = [.. updates
            .Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepStartedEvent>()
            .Select(static evt => evt.StepName)];
        string[] finished = [.. updates
            .Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepFinishedEvent>()
            .Select(static evt => evt.StepName)];

        int writerStart = Array.FindIndex(started, static name => name.StartsWith("Writer_", StringComparison.Ordinal));
        int reviewerStart = Array.FindIndex(started, static name => name.StartsWith("Reviewer_", StringComparison.Ordinal));
        int writerFinish = Array.FindIndex(finished, static name => name.StartsWith("Writer_", StringComparison.Ordinal));
        int reviewerFinish = Array.FindIndex(finished, static name => name.StartsWith("Reviewer_", StringComparison.Ordinal));

        writerStart.Should().BeGreaterThanOrEqualTo(0);
        reviewerStart.Should().BeGreaterThan(writerStart);
        writerFinish.Should().BeGreaterThanOrEqualTo(0);
        reviewerFinish.Should().BeGreaterThan(writerFinish);
        updates.Count(static update => update.Text == "draft").Should().Be(1);
        updates.Count(static update => update.Text == "final").Should().Be(1);
    }
}
