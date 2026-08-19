// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.WorkflowConcurrent;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class ConcurrentWorkflowTests
{
    [Fact]
    public async Task ClientReceivesIndependentExecutorStepsAsync()
    {
        // Arrange
        AIAgent researcher = new DeterministicAgent("Researcher", "facts");
        AIAgent critic = new DeterministicAgent("Critic", "risks");
        Workflow workflow = ConcurrentWorkflow.Create(researcher, critic);
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(
            workflow.AsAIAgent(name: "ConcurrentWorkflow"));
        AGUIChatClient chatClient = new(new(host.Client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(name: "client");
        AgentSession session = await clientAgent.CreateSessionAsync();

        // Act
        List<AgentResponseUpdate> updates = await clientAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"), session)
            .ToListAsync();

        // Assert
        object?[] lifecycle = [.. updates
            .Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .Where(static raw => raw is StepStartedEvent or StepFinishedEvent)];

        int researcherStart = Array.FindIndex(lifecycle, static raw =>
            raw is StepStartedEvent evt && evt.StepName.StartsWith("Researcher_", StringComparison.Ordinal));
        int criticStart = Array.FindIndex(lifecycle, static raw =>
            raw is StepStartedEvent evt && evt.StepName.StartsWith("Critic_", StringComparison.Ordinal));
        int researcherFinish = Array.FindIndex(lifecycle, static raw =>
            raw is StepFinishedEvent evt && evt.StepName.StartsWith("Researcher_", StringComparison.Ordinal));
        int criticFinish = Array.FindIndex(lifecycle, static raw =>
            raw is StepFinishedEvent evt && evt.StepName.StartsWith("Critic_", StringComparison.Ordinal));

        researcherStart.Should().BeGreaterThanOrEqualTo(0);
        criticStart.Should().BeGreaterThanOrEqualTo(0);
        researcherFinish.Should().BeGreaterThan(researcherStart);
        criticFinish.Should().BeGreaterThan(criticStart);
        updates.Count(static update => update.Text == "facts").Should().Be(1);
        updates.Count(static update => update.Text == "risks").Should().Be(1);
    }
}
