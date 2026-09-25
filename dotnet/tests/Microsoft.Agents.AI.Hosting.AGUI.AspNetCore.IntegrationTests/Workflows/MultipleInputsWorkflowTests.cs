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
using AGUI.WorkflowMultipleInputs;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.Workflows;

public sealed class MultipleInputsWorkflowTests
{
    [Fact]
    public async Task ClientRespondsPartiallyOutOfOrderThenCompletesWorkflowAsync()
    {
        // Arrange
        AIAgent workflowAgent = MultipleInputsWorkflow.Create().AsAIAgent(name: "MultipleInputsWorkflow");
        await using WorkflowTestHost host = await WorkflowTestHost.StartAsync(workflowAgent, persistSession: true);
        RunAgentInput initialInput = new()
        {
            Messages = new[] { new ChatMessage(ChatRole.User, "plan trip") }.AsAGUIMessages().ToList(),
            RunId = "travel-run-1",
            ThreadId = "travel-thread",
        };

        // Act - collect three same-turn interruptions.
        List<BaseEvent> firstTurn = await SendAsync(host.Client, initialInput);
        RunFinishedEvent firstFinished = firstTurn.OfType<RunFinishedEvent>().Single();
        AGUIInterrupt[] requests =
        [
            .. firstFinished.Outcome.Should().BeOfType<RunFinishedInterruptOutcome>().Subject.Interrupts,
        ];
        requests.Should().HaveCount(3);
        AGUIInterrupt dates = requests.Single(static item => item.Message!.Contains("TravelDates"));
        AGUIInterrupt travelers = requests.Single(static item => item.Message!.Contains("TravelerDetails"));
        AGUIInterrupt preferences = requests.Single(static item => item.Message!.Contains("TravelPreferences"));

        // Respond to traveler details before dates, leaving preferences pending.
        List<BaseEvent> partialTurn = await SendAsync(host.Client, CreateResume(
            firstFinished,
            "travel-run-2",
            [
                Resume(travelers, new { kind = "travelers", count = 2 }),
                Resume(dates, new { kind = "dates", departure = "2026-10-10", returnDate = "2026-10-14" }),
            ]));
        partialTurn.OfType<TextMessageContentEvent>().Should().BeEmpty();
        RunFinishedEvent partialFinished = partialTurn.OfType<RunFinishedEvent>().Single();

        List<BaseEvent> finalTurn = await SendAsync(host.Client, CreateResume(
            partialFinished,
            "travel-run-3",
            [Resume(preferences, new { kind = "preferences", budget = 2500 })]));

        // Assert
        string text = string.Concat(finalTurn.OfType<TextMessageContentEvent>().Select(static evt => evt.Delta));
        text.Should().Contain("Travel plan ready for Seattle");
    }

    private static RunAgentInput CreateResume(
        RunFinishedEvent previous,
        string runId,
        IList<AGUIResume> resumes)
        => new()
        {
            Messages = [],
            ParentRunId = previous.RunId,
            Resume = resumes,
            RunId = runId,
            ThreadId = previous.ThreadId,
        };

    private static AGUIResume Resume(AGUIInterrupt interrupt, object payload)
        => new()
        {
            InterruptId = interrupt.Id,
            Payload = JsonSerializer.SerializeToElement(payload),
            Status = "resolved",
        };

    private static async Task<List<BaseEvent>> SendAsync(HttpClient client, RunAgentInput input)
    {
        using JsonContent content = JsonContent.Create(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        using HttpResponseMessage response = await client.PostAsync(new Uri("", UriKind.Relative), content);
        response.EnsureSuccessStatusCode();
        return await response.ReadAGUIEventStreamAsync().ToListAsync();
    }
}
