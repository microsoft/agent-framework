// Copyright (c) Microsoft. All rights reserved.

//using System.Collections.Generic;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MagenticManagerTests
{
    private static void CheckMessage(ChatMessage message, string expectedText, bool runPropertySmokeTest = false, bool skipCreatedAt = true)
    {
        Assert.Equal(expectedText, message.Text);

        if (runPropertySmokeTest)
        {
            Assert.Equal(nameof(MagenticOrchestrator), message.AuthorName);

            if (!skipCreatedAt)
            {
                Assert.NotNull(message.CreatedAt);
                Assert.True(message.CreatedAt >= DateTimeOffset.UtcNow.AddDays(-1));
            }

            Assert.Equal(ChatRole.Assistant, message.Role);
            Assert.NotNull(message.MessageId);
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

        Assert.Equal(4, taskContext.ChatHistory.Count);

        if (hasExistingPlan)
        {
            ChatMessage factsRequest = taskContext.ChatHistory[0];
            Assert.Contains("OldFacts", factsRequest.Text);
        }

        ChatMessage facts = taskContext.ChatHistory[1];
        Assert.Equal(newPlan.CurrentFacts, facts);

        ChatMessage plan = taskContext.ChatHistory[3];
        Assert.Equal(newPlan.CurrentPlan, plan);
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

        Assert.Equal(failures, turns.Count);
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
        Assert.False(taskContext.ProgressLedger.IsStarted);

        Task actionAsync() => manager.UpdateProgressLedgerAsync(taskContext, workflowContext, CancellationToken.None).AsTask();

        if (failures >= taskContext.TaskLimits.MaxProgressLedgerRetryCount)
        {
            // We expect to see an exception if the number of failures exceeds the maximum retry count
            Exception? exception = await Record.ExceptionAsync(actionAsync);
            Assert.NotNull(exception);
            Assert.False(taskContext.ProgressLedger.IsStarted);
        }
        else
        {
            Assert.Null(await Record.ExceptionAsync(actionAsync));
            Assert.True(taskContext.ProgressLedger.IsStarted);
            TestProgressLedgerState.Default.Validate(taskContext.ProgressLedger);
        }

        int expectedWarnings = Math.Min(failures, 3);

        Assert.Equal(expectedWarnings, runContext.Events.Count);
        Assert.All(runContext.Events, e => Assert.IsType<WorkflowWarningEvent>(e));
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
