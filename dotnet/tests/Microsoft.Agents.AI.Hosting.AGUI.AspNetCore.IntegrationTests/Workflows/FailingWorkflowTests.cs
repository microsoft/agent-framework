// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
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
        RunAgentInput input = new()
        {
            Messages = new[] { new ChatMessage(ChatRole.User, "start") }.AsAGUIMessages().ToList(),
            RunId = "failure-run",
            ThreadId = "failure-thread",
        };

        // Act
        List<BaseEvent> events = await SendAsync(host.Client, input);

        // Assert
        int stepStarted = events.FindIndex(static evt =>
            evt is StepStartedEvent step
            && step.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        int stepFinished = events.FindIndex(static evt =>
            evt is StepFinishedEvent step
            && step.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        int textEnd = events.FindLastIndex(static evt => evt is TextMessageEndEvent);
        int runError = events.FindIndex(static evt => evt is RunErrorEvent);

        stepStarted.Should().BeGreaterThanOrEqualTo(0);
        stepFinished.Should().BeGreaterThan(stepStarted);
        textEnd.Should().BeGreaterThan(stepFinished);
        runError.Should().BeGreaterThan(stepFinished);
        runError.Should().BeGreaterThan(textEnd);
        events[runError].Should().BeOfType<RunErrorEvent>()
            .Which.Message.Should().Be("An error occurred while executing the workflow.");
        events.Skip(runError + 1).Should().BeEmpty();
        events.OfType<RunFinishedEvent>().Should().BeEmpty();
        events.OfType<TextMessageStartEvent>().Should().ContainSingle();
        events.OfType<TextMessageEndEvent>().Should().ContainSingle();

        int startedCount = events
            .OfType<StepStartedEvent>()
            .Count(static evt => evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        int finishedCount = events
            .OfType<StepFinishedEvent>()
            .Count(static evt => evt.StepName.StartsWith("FailingStep_", StringComparison.Ordinal));
        startedCount.Should().BeGreaterThan(0);
        finishedCount.Should().Be(startedCount);
    }

    private static async Task<List<BaseEvent>> SendAsync(HttpClient client, RunAgentInput input)
    {
        using JsonContent content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        using HttpResponseMessage response = await client.PostAsync(new Uri("", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        return await response.ReadAGUIEventStreamAsync().ToListAsync();
    }
}
