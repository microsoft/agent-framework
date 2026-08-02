// Copyright (c) Microsoft. All rights reserved.

//using System.Collections.Generic;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MagenticManagerTests
{
    private static void CheckMessage(ChatMessage message, string expectedText, bool runPropertySmokeTest = false, bool skipCreatedAt = true)
    {
        message.Text.Should().Be(expectedText);

        if (runPropertySmokeTest)
        {
            message.AuthorName.Should().Be(nameof(MagenticOrchestrator));

            if (!skipCreatedAt)
            {
                message.CreatedAt.Should().NotBeNull().And.NotBeBefore(DateTimeOffset.UtcNow.AddDays(-1));
            }

            message.Role.Should().Be(ChatRole.Assistant);
            message.MessageId.Should().NotBeNull();
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_MagenticManager_UpdatePlanAsync(bool hasExistingPlan)
    {
        TestReplayAgent testAgent = new(name: nameof(MagenticOrchestrator),
                                        messages:
                                        [
                                            [new(ChatRole.Assistant, "Facts")],
                                            [new(ChatRole.Assistant, "Plan")],
                                        ]);

        TestEchoAgent participant = new(name: "Echo");
        MagenticManager manager = new(testAgent);

        MagenticTaskContext taskContext = new([new(ChatRole.User, "Task")], [participant], new TaskLimits(), null, []);
        if (hasExistingPlan)
        {
            taskContext.TaskLedger = new(new(ChatRole.Assistant, "OldFacts"), new(ChatRole.Assistant, "OldPlan"));
        }

        TestRunContext runContext = new();
        IWorkflowContext workflowContext = runContext.BindWorkflowContext(nameof(MagenticOrchestrator));

        TaskLedger newPlan = await manager.UpdatePlanAsync(taskContext, workflowContext, CancellationToken.None);
        CheckMessage(newPlan.CurrentFacts, "Facts");
        CheckMessage(newPlan.CurrentPlan, "Plan");

        taskContext.ChatHistory.Should().HaveCount(4);

        if (hasExistingPlan)
        {
            ChatMessage factsRequest = taskContext.ChatHistory[0];
            factsRequest.Text.Should().Contain("OldFacts");
        }

        ChatMessage facts = taskContext.ChatHistory[1];
        facts.Should().Be(newPlan.CurrentFacts);

        ChatMessage plan = taskContext.ChatHistory[3];
        plan.Should().Be(newPlan.CurrentPlan);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    public async Task Test_MagenticManager_UpdateProgressLedgerAsync(int failures)
    {
        List<List<ChatMessage>> turns =
            TestProgressLedgerState.MissingRequired.Take(failures)
                                                   .Select<TestProgressLedgerState, List<ChatMessage>>(
                                                        state => [new ChatMessage(ChatRole.Assistant, state.ToJsonString())])
                                                   .ToList();

        turns.Should().HaveCount(failures);
        turns.Add([new ChatMessage(ChatRole.Assistant, TestProgressLedgerState.Default.ToJsonString())]);

        TestReplayAgent testAgent = new(name: nameof(MagenticOrchestrator),
                                        messages: turns);

        TestEchoAgent participant = new(name: "Echo");
        MagenticManager manager = new(testAgent);

        MagenticTaskContext taskContext = new([new(ChatRole.User, "Task")], [participant], new TaskLimits(), null, []);
        taskContext.TaskLedger = new(new(ChatRole.Assistant, "OldFacts"), new(ChatRole.Assistant, "OldPlan"));

        TestRunContext runContext = new();
        IWorkflowContext workflowContext = runContext.BindWorkflowContext(nameof(MagenticOrchestrator));

        // Precondition check: ProgressLedger should be not "started"
        taskContext.ProgressLedger.IsStarted.Should().BeFalse();

        Func<Task> action = () => manager.UpdateProgressLedgerAsync(taskContext, workflowContext, CancellationToken.None).AsTask();

        if (failures >= taskContext.TaskLimits.MaxProgressLedgerRetryCount)
        {
            // We expect to see an exception if the number of failures exceeds the maximum retry count
            await action.Should().ThrowAsync();
            taskContext.ProgressLedger.IsStarted.Should().BeFalse();
        }
        else
        {
            await action.Should().NotThrowAsync();
            taskContext.ProgressLedger.IsStarted.Should().BeTrue();
            TestProgressLedgerState.Default.Validate(taskContext.ProgressLedger);
        }

        int expectedWarnings = Math.Min(failures, 3);

        runContext.Events.Should().HaveCount(expectedWarnings).And.AllBeOfType<WorkflowWarningEvent>();
    }

    [Fact]
    public async Task Test_MagenticManager_PrepareFinalAnswerAsync()
    {
        TestReplayAgent testAgent = new(name: nameof(MagenticOrchestrator),
                                        messages:
                                        [
                                            [
                                                new(ChatRole.Assistant, "FinalAnswer")
                                            ],
                                        ]);

        TestEchoAgent participant = new(name: "Echo");
        MagenticManager manager = new(testAgent);

        MagenticTaskContext taskContext = new([new(ChatRole.User, "Task")], [participant], new TaskLimits(), null, []);

        TestRunContext runContext = new();
        IWorkflowContext workflowContext = runContext.BindWorkflowContext(nameof(MagenticOrchestrator));

        ChatMessage answer = await manager.PrepareFinalAnswerAsync(taskContext, workflowContext, CancellationToken.None);

        CheckMessage(answer, "FinalAnswer", true, false);
    }
}
