// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;
using AGUI.Abstractions;
using AGUI.Client;
using AGUI.WorkflowApproval;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class ApprovalWorkflowTests
{
    [Fact]
    public async Task ClientApprovesInterruptionAndWorkflowResumesAsync()
    {
        // Arrange
        AIAgent workflowAgent = ApprovalWorkflow.Create().AsAIAgent(
            name: "ApprovalWorkflow",
            includeWorkflowOutputsInResponse: true);
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(workflowAgent, persistSession: true);
        RunAgentInput initialInput = new()
        {
            Messages = new[] { new ChatMessage(ChatRole.User, "submit") }.AsAGUIMessages().ToList(),
            RunId = "approval-run-1",
            ThreadId = "approval-thread",
        };

        // Act - initial run pauses for approval.
        List<BaseEvent> firstTurn = await SendAsync(host.Client, initialInput);
        RunFinishedEvent finished = firstTurn.OfType<RunFinishedEvent>().Single();
        RunFinishedInterruptOutcome outcome = finished.Outcome.Should()
            .BeOfType<RunFinishedInterruptOutcome>().Subject;
        AGUIInterrupt interrupt = outcome.Interrupts.Should().ContainSingle().Subject;
        interrupt.Reason.Should().Be(InterruptReasons.InputRequired);

        RunAgentInput resumeInput = new()
        {
            Messages = [],
            ParentRunId = finished.RunId,
            Resume =
            [
                new AGUIResume
                {
                    InterruptId = interrupt.Id,
                    Payload = JsonSerializer.SerializeToElement(new { approved = true }),
                    Status = "resolved",
                },
            ],
            RunId = "approval-run-2",
            ThreadId = finished.ThreadId,
        };
        List<BaseEvent> secondTurn = await SendAsync(host.Client, resumeInput);

        // Assert
        string text = string.Concat(secondTurn.OfType<TextMessageContentEvent>().Select(static evt => evt.Delta));
        text.Should().Contain(
            "Expense approved and submitted.",
            "events were {0}",
            string.Join(", ", secondTurn.Select(static evt => evt.GetType().Name)));
        secondTurn.OfType<StepStartedEvent>()
            .Should().Contain(static evt => evt.StepName == "ExpenseApproval");
    }

    private static async Task<List<BaseEvent>> SendAsync(HttpClient client, RunAgentInput input)
    {
        using JsonContent content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        using HttpResponseMessage response = await client.PostAsync(new Uri("", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        return await response.ReadAGUIEventStreamAsync().ToListAsync();
    }
}
