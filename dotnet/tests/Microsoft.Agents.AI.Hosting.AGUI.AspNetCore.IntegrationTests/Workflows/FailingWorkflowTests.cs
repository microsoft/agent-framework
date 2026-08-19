// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.WorkflowFailure;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class FailingWorkflowTests
{
    [Fact]
    public async Task ClientReceivesStepFinishedForFailedExecutorAsync()
    {
        // Arrange
        Workflow workflow = FailingWorkflow.Create(new FailingAgent());
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(
            workflow.AsAIAgent(name: "FailingWorkflow"));
        AGUIChatClient chatClient = new(new(host.Client, ""));
        AIAgent clientAgent = chatClient.AsAIAgent(name: "client");
        AgentSession session = await clientAgent.CreateSessionAsync();

        // Act
        List<AgentResponseUpdate> updates = await clientAgent
            .RunStreamingAsync(new ChatMessage(ChatRole.User, "start"), session)
            .ToListAsync();

        // Assert
        int stepStarted = updates.FindIndex(static update =>
            update.AsChatResponseUpdate().RawRepresentation is StepStartedEvent evt
            && evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        int stepFinished = updates.FindIndex(static update =>
            update.AsChatResponseUpdate().RawRepresentation is StepFinishedEvent evt
            && evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        stepStarted.Should().BeGreaterThanOrEqualTo(0);
        stepFinished.Should().BeGreaterThan(stepStarted);
        int startedCount = updates.Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepStartedEvent>()
            .Count(static evt => evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        int finishedCount = updates.Select(static update => update.AsChatResponseUpdate().RawRepresentation)
            .OfType<StepFinishedEvent>()
            .Count(static evt => evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        startedCount.Should().BeGreaterThan(0);
        finishedCount.Should().Be(startedCount);
    }
}
