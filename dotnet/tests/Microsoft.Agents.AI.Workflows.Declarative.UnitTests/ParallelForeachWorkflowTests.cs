// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests;

/// <summary>
/// End-to-end behavioral tests for parallel declarative <c>Foreach</c> execution.
/// </summary>
public sealed class ParallelForeachWorkflowTests
{
    [Fact]
    public async Task ForeachRemainsSequentialByDefaultAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new();
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\"]",
            executionOptions: null,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(3, provider.InvocationCount);
        Assert.Equal(1, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachExecutesConcurrentlyAndHonorsLimitAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 2, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\", \"e\", \"f\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
                  timeoutInMilliseconds: 5000
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(6, provider.InvocationCount);
        Assert.Equal(2, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachWithOneWorkerRemainsSerializedAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(delayByIndex: index => TimeSpan.FromMilliseconds((2 - index) * 25));
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 1
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:a", "1:b", "2:c"], GetAgentResponses(observation));
        Assert.Equal([0, 1, 2], provider.Completions);
        Assert.Equal(1, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachUsesBoundedDefaultLimitAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 4, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\", \"e\", \"f\"]",
            executionOptions: """
                  mode: Parallel
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(6, provider.InvocationCount);
        Assert.Equal(4, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachCapsWorkerCountAtItemCountForExtremeLimitAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 2, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2147483647
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(2, provider.InvocationCount);
        Assert.Equal(2, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachPreservesBlankAndExtremeItemValuesAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 4, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[Blank(), -2147483648, 0, 2147483647]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(4, provider.InvocationCount);
        Assert.Equal(
            ["0:", "1:-2147483648", "2:0", "3:2147483647"],
            GetAgentResponses(observation));
    }

    [Fact]
    public async Task ParallelForeachKeepsDuplicateValuesSeparatedByIndexAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 3, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"same\", \"same\", \"same\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 3
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:same", "1:same", "2:same"], GetAgentResponses(observation));
        Assert.Equal(3, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachIsolatesStateAndCommitsInSourceOrderAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            delayByIndex: index => TimeSpan.FromMilliseconds((3 - index) * 100));
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: $$"""
                    - kind: SetVariable
                      id: capture_last
                      variable: Local.LastValue
                      value: =Local.Item

            {{InvokeAgentAction}}
            """,
            afterActions: """
                - kind: SendActivity
                  id: report_final
                  activity: Final {Local.LastValue}
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(s_orderedResponses, GetAgentResponses(observation));
        Assert.Contains(observation.Events.OfType<MessageActivityEvent>(), evt => evt.Message.Trim() == "Final d");
        Assert.Equal([3, 2, 1, 0], provider.Completions);
        Assert.Equal(
            s_orderedResponses,
            provider.Invocations.OrderBy(invocation => invocation.Index).Select(invocation => $"{invocation.Index}:{invocation.Value}"));
    }

    [Fact]
    public async Task ParallelForeachStagesWorkflowConversationWritesInSourceOrderAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            delayByIndex: index => TimeSpan.FromMilliseconds((3 - index) * 100),
            conversationWriteDelay: TimeSpan.FromMilliseconds(25));
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(s_orderedResponses, provider.WorkflowConversationWrites);
        Assert.Equal(1, provider.PeakConversationWriteConcurrency);
        Assert.Equal(provider.InvocationCount, provider.InvocationCompletionsAtFirstConversationWrite);
    }

    [Fact]
    public async Task ParallelForeachDoesNotWriteWorkflowConversationWhenAnIterationFailsAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            delayByIndex: index => TimeSpan.FromMilliseconds((3 - index) * 50),
            failureIndexes: [2],
            conversationWriteDelay: TimeSpan.FromMilliseconds(10));
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertWorkflowError(observation);
        Assert.Empty(provider.WorkflowConversationWrites);
    }

    [Fact]
    public async Task ParallelForeachConversationReplayCannotMutateBufferedEventsAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(mutateConversationWrites: true);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:a", "1:b"], GetAgentResponses(observation));
        Assert.Equal(["0:a", "1:b"], provider.WorkflowConversationWrites);
    }

    [Fact]
    public async Task NestedParallelForeachKeepsConversationWritesStagedUntilTheOuterCommitAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 2,
            barrierTimeout: s_barrierTimeout,
            delayByIndex: index => TimeSpan.FromMilliseconds((1 - index) * 50),
            conversationWriteDelay: TimeSpan.FromMilliseconds(15));
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: Foreach
                      id: inner_parallel_loop
                      items: =[1, 2]
                      value: Local.InnerItem
                      index: Local.InnerIndex
                      mode: Parallel
                      maxParallelism: 2
                      actions:
                        - kind: InvokeAzureAgent
                          id: nested_invoke_agent
                          agent:
                            name: TestAgent
                          input:
                            arguments:
                              value: =Concatenate(Text(Local.Index), ":", Text(Local.InnerIndex), ":", Local.Item)
                              index: =Local.InnerIndex
                          output:
                            autoSend: true
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:0:0:a", "1:0:1:a", "0:1:0:b", "1:1:1:b"], provider.WorkflowConversationWrites);
        Assert.Equal(1, provider.PeakConversationWriteConcurrency);
    }

    [Fact]
    public async Task NestedParallelForeachHonorsTheProductOfLimitsAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 4, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: Foreach
                      id: inner_parallel_loop
                      items: =[1, 2]
                      value: Local.InnerItem
                      index: Local.InnerIndex
                      mode: Parallel
                      maxParallelism: 2
                      actions:
                        - kind: InvokeAzureAgent
                          id: nested_invoke_agent
                          agent:
                            name: TestAgent
                          input:
                            arguments:
                              value: =Local.Item
                              index: =Local.InnerIndex
                          output:
                            autoSend: false
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(4, provider.InvocationCount);
        Assert.Equal(4, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachDeepCopiesComplexLoopValuesAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 2, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[Local.Shared, Local.Shared]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: EditTable
                      id: mutate_item
                      itemsVariable: Local.Item
                      changeType: Add
                      value: ={ id: Local.Index }

                    - kind: InvokeAzureAgent
                      id: invoke_agent
                      agent:
                        name: TestAgent
                      input:
                        arguments:
                          value: =Text(CountRows(Local.Item))
                          index: =Local.Index
                      output:
                        autoSend: true
            """,
            afterActions: """
                - kind: SendActivity
                  id: report_shared_count
                  activity: Shared {CountRows(Local.Shared)}
            """,
            beforeActions: """
                - kind: SetVariable
                  id: initialize_shared
                  variable: Local.Shared
                  value: =[{ id: -1 }]
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:2", "1:2"], GetAgentResponses(observation));
        Assert.Contains(observation.Events.OfType<MessageActivityEvent>(), evt => evt.Message.Trim() == "Shared 1");
    }

    [Fact]
    public async Task ParallelForeachAggregatesBranchFailureAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            failureIndexes: [1]);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: $$"""
                    - kind: SendActivity
                      id: buffered_before_failure
                      activity: Branch {Local.Index}

            {{InvokeAgentAction}}
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        Assert.Contains(Flatten(error), exception => exception is AggregateException);
        Assert.Contains(Flatten(error), exception => exception.Message.Contains("iteration 1", StringComparison.OrdinalIgnoreCase));
        Assert.Empty(GetAgentResponses(observation));
        Assert.DoesNotContain(observation.Events.OfType<MessageActivityEvent>(), evt => evt.Message.Trim().StartsWith("Branch ", StringComparison.Ordinal));
    }

    [Fact]
    public async Task ParallelForeachRetainsSimultaneousBranchFailuresInSourceOrderAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            failureIndexes: [1, 3],
            failureBarrierParticipants: 2);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        AggregateException aggregate = Assert.Single(
            Flatten(error).OfType<AggregateException>(),
            exception => exception.Message.StartsWith("Parallel Foreach 'parallel_loop' failed.", StringComparison.Ordinal));
        string[] iterationFailures = [.. aggregate.InnerExceptions.Select(exception => exception.Message)];
        Assert.Equal(
            [
                "Parallel Foreach 'parallel_loop' iteration 1 failed.",
                "Parallel Foreach 'parallel_loop' iteration 3 failed.",
            ],
            iterationFailures);
    }

    [Fact]
    public async Task ParallelForeachFailureCancelsActivePeersAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(
            barrierParticipants: 4,
            barrierTimeout: s_barrierTimeout,
            failureIndexes: [0],
            waitUntilCanceledIndexes: [1, 2, 3]);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\", \"c\", \"d\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 4
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        Assert.Contains(Flatten(error), exception => exception.Message.Contains("iteration 0", StringComparison.OrdinalIgnoreCase));
        await AwaitWithTimeoutAsync(provider.CancellationObserved, TimeSpan.FromSeconds(5));
        await AwaitWithTimeoutAsync(provider.NoActiveInvocations, TimeSpan.FromSeconds(5));
        Assert.Equal(0, provider.ActiveCount);
        Assert.Empty(GetAgentResponses(observation));
    }

    [Fact]
    public async Task ParallelForeachPropagatesCancellationAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(waitUntilCanceled: true);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: InvokeAgentAction);
        Workflow workflow = BuildWorkflow(yaml, provider);
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "input");
        Task<WorkflowEvent[]> watchTask = CollectEventsAsync(run);
        await AwaitWithTimeoutAsync(provider.FirstInvocationStarted, TimeSpan.FromSeconds(5));

        // Act
        await run.CancelRunAsync();
        WorkflowEvent[] events = await AwaitWithTimeoutAsync(watchTask, TimeSpan.FromSeconds(5));
        RunStatus status = await run.GetStatusAsync();

        // Assert
        Assert.Equal(RunStatus.Ended, status);
        await AwaitWithTimeoutAsync(provider.CancellationObserved, TimeSpan.FromSeconds(5));
        await AwaitWithTimeoutAsync(provider.NoActiveInvocations, TimeSpan.FromSeconds(5));
        Assert.Equal(0, provider.ActiveCount);
        Assert.DoesNotContain(events.OfType<DeclarativeActionCompletedEvent>(), evt => evt.ActionId == "parallel_loop");
        Assert.DoesNotContain(events.OfType<DeclarativeActionInvokedEvent>(), evt => evt.ActionId == "invoke_agent");
    }

    [Fact]
    public async Task ParallelForeachTimesOutIterationAndCancelsPeersAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(waitUntilCanceled: true);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
                  timeoutInMilliseconds: 1000
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        Assert.Contains(Flatten(error), exception => exception is TimeoutException);
        await AwaitWithTimeoutAsync(provider.CancellationObserved, TimeSpan.FromSeconds(5));
        await AwaitWithTimeoutAsync(provider.NoActiveInvocations, TimeSpan.FromSeconds(5));
        Assert.Equal(0, provider.ActiveCount);
        Assert.Empty(GetAgentResponses(observation));
        Assert.DoesNotContain(observation.Events.OfType<DeclarativeActionInvokedEvent>(), evt => evt.ActionId == "invoke_agent");
    }

    [Fact]
    public async Task ParallelForeachHandlesEmptyCollectionAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new();
        string yaml = CreateWorkflowYaml(
            items: "=[]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 3
            """,
            bodyActions: InvokeAgentAction,
            afterActions: """
                - kind: SendActivity
                  id: empty_complete
                  activity: empty complete
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(0, provider.InvocationCount);
        Assert.Contains(observation.Events.OfType<DeclarativeActionCompletedEvent>(), evt => evt.ActionId == "parallel_loop");
        Assert.Contains(observation.Events.OfType<MessageActivityEvent>(), evt => evt.Message.Trim() == "empty complete");
    }

    [Fact]
    public async Task ParallelForeachCheckpointResumesAfterCommittedIterationsAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 2, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: $$"""
                    - kind: SetVariable
                      id: capture_checkpoint_value
                      variable: Local.LastValue
                      value: =Local.Item

            {{InvokeAgentAction}}
            """,
            afterActions: """
                - kind: SendActivity
                  id: after_parallel
                  activity: after {Local.LastValue}
            """);
        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        CheckpointInfo? checkpointAfterLoop = null;
        bool loopCompleted = false;

        // Act
        await using (StreamingRun firstRun = await InProcessExecution.RunStreamingAsync(
            BuildWorkflow(yaml, provider),
            "input",
            checkpointManager))
        {
            await foreach (WorkflowEvent workflowEvent in firstRun.WatchStreamAsync())
            {
                if (workflowEvent is DeclarativeActionCompletedEvent { ActionId: "parallel_loop" })
                {
                    loopCompleted = true;
                }

                if (loopCompleted &&
                    checkpointAfterLoop is null &&
                    workflowEvent is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    checkpointAfterLoop = checkpoint;
                }
            }
        }

        int invocationCountBeforeResume = provider.InvocationCount;
        await using StreamingRun resumedRun = await InProcessExecution.ResumeStreamingAsync(
            BuildWorkflow(yaml, provider),
            Assert.IsType<CheckpointInfo>(checkpointAfterLoop),
            checkpointManager);
        WorkflowEvent[] resumedEvents = await CollectEventsAsync(resumedRun);

        // Assert
        Assert.Equal(2, invocationCountBeforeResume);
        Assert.Equal(invocationCountBeforeResume, provider.InvocationCount);
        Assert.DoesNotContain(resumedEvents.OfType<DeclarativeActionInvokedEvent>(), evt => evt.ActionId == "parallel_loop");
        Assert.DoesNotContain(resumedEvents, workflowEvent => workflowEvent is AgentResponseEvent { ExecutorId: "invoke_agent" });
        Assert.Contains(resumedEvents.OfType<MessageActivityEvent>(), evt => evt.Message.Trim() == "after b");
    }

    [Theory]
    [InlineData("Parallel", 0)]
    [InlineData("Parallel", -1)]
    [InlineData("unsupported", 2)]
    [InlineData("\"1\"", 2)]
    [InlineData("Sequential, Parallel", 2)]
    [InlineData("null", 2)]
    [InlineData("true", 2)]
    public void ParallelForeachRejectsInvalidConfiguration(string mode, int maxParallelism)
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: $$"""
                  mode: {{mode}}
                  maxParallelism: {{maxParallelism}}
            """,
            bodyActions: InvokeAgentAction);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("parallel", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void ParallelForeachRejectsInvalidTimeout(int timeoutInMilliseconds)
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: $$"""
                  mode: Parallel
                  maxParallelism: 2
                  timeoutInMilliseconds: {{timeoutInMilliseconds}}
            """,
            bodyActions: InvokeAgentAction);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("timeout", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("1.5")]
    [InlineData("2147483648")]
    [InlineData("\"2\"")]
    [InlineData("-2147483649")]
    [InlineData("null")]
    [InlineData("true")]
    public void ParallelForeachRejectsNonIntegerOrOutOfRangeMaxParallelism(string maxParallelism)
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: $$"""
                  mode: Parallel
                  maxParallelism: {{maxParallelism}}
            """,
            bodyActions: InvokeAgentAction);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("maxParallelism", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("1.5")]
    [InlineData("2147483648")]
    [InlineData("\"1000\"")]
    [InlineData("-2147483649")]
    [InlineData("null")]
    [InlineData("true")]
    public void ParallelForeachRejectsNonIntegerOrOutOfRangeTimeout(string timeoutInMilliseconds)
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: $$"""
                  mode: Parallel
                  timeoutInMilliseconds: {{timeoutInMilliseconds}}
            """,
            bodyActions: InvokeAgentAction);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("timeout", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ParallelForeachRejectsCheckpointingBody()
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: Question
                      id: prompt_in_loop
                      alwaysPrompt: true
                      autoSend: false
                      property: Local.Answer
                      prompt:
                        kind: Message
                        text:
                          - answer
                      entity:
                        kind: StringPrebuiltEntity
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("checkpoint", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ParallelForeachRejectsConversationTermination()
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: EndConversation
                      id: end_conversation_in_parallel
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("terminates", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ParallelForeachRejectsGotoOutsideBody()
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: GotoAction
                      id: goto_after_parallel
                      actionId: after_parallel
            """,
            afterActions: """
                - kind: SendActivity
                  id: after_parallel
                  activity: after
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("GotoAction", exception.Message, StringComparison.Ordinal);
        Assert.Contains("parallel", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParallelForeachAllowsGotoWithinBodyAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new();
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: $$"""
                    - kind: GotoAction
                      id: goto_agent
                      actionId: invoke_agent

                    - kind: SendActivity
                      id: skipped_activity
                      activity: never

            {{InvokeAgentAction}}
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:a"], GetAgentResponses(observation));
        Assert.DoesNotContain(observation.Events.OfType<MessageActivityEvent>(), evt => evt.Message.Trim() == "never");
    }

    [Fact]
    public void ParallelForeachRejectsFunctionToolCheckpoint()
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: InvokeFunctionTool
                      id: invoke_function_tool
                      functionName: TestFunction
                      requireApproval: false
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("external input", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("EndWorkflow", "terminates")]
    [InlineData("AddConversationMessage", "conversation")]
    [InlineData("CopyConversationMessages", "conversation")]
    [InlineData("InvokeMcpTool", "external input")]
    [InlineData("HttpRequestAction", "conversation")]
    public void ParallelForeachRejectsUnsafeBodyActions(string actionKind, string expectedMessagePart)
    {
        // Arrange
        string action = actionKind switch
        {
            "EndWorkflow" => """
                    - kind: EndWorkflow
                      id: end_workflow_in_parallel
            """,
            "AddConversationMessage" => """
                    - kind: AddConversationMessage
                      id: add_message_in_parallel
                      message: Local.Message
                      role: User
                      conversationId: =System.ConversationId
                      content:
                        - type: Text
                          value: parallel
            """,
            "CopyConversationMessages" => """
                    - kind: CopyConversationMessages
                      id: copy_messages_in_parallel
                      conversationId: =System.ConversationId
                      messages: =[UserMessage("parallel")]
            """,
            "InvokeMcpTool" => """
                    - kind: InvokeMcpTool
                      id: invoke_mcp_in_parallel
                      serverUrl: https://example.test/mcp
                      toolName: test
            """,
            "HttpRequestAction" => """
                    - kind: HttpRequestAction
                      id: http_in_parallel
                      method: GET
                      url: https://example.test
                      conversationId: =System.ConversationId
            """,
            _ => throw new ArgumentOutOfRangeException(nameof(actionKind), actionKind, null),
        };
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: action);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains(expectedMessagePart, exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ParallelForeachRejectsExplicitAgentConversationTarget()
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: """
                    - kind: InvokeAzureAgent
                      id: explicit_conversation_agent
                      conversationId: =System.ConversationId
                      agent:
                        name: TestAgent
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains("conversation target", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("BreakLoop")]
    [InlineData("ContinueLoop")]
    public void ParallelForeachRejectsOuterLoopControl(string actionKind)
    {
        // Arrange
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: $$"""
                    - kind: {{actionKind}}
                      id: unsupported_loop_control
            """);

        // Act
        DeclarativeModelException exception = Assert.Throws<DeclarativeModelException>(() => BuildWorkflow(yaml, new ControlledAgentProvider()));

        // Assert
        Assert.Contains(actionKind, exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("BreakLoop")]
    [InlineData("ContinueLoop")]
    public async Task ParallelForeachAllowsNestedSequentialLoopControlAsync(string actionKind)
    {
        // Arrange
        ControlledAgentProvider provider = new(barrierParticipants: 2, barrierTimeout: s_barrierTimeout);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\", \"b\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: $$"""
                    - kind: Foreach
                      id: inner_loop
                      items: =[1, 2]
                      value: Local.InnerItem
                      index: Local.InnerIndex
                      actions:
                        - kind: {{actionKind}}
                          id: control_inner_loop

            {{InvokeAgentAction}}
            """);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        AssertNoWorkflowError(observation);
        Assert.Equal(["0:a", "1:b"], GetAgentResponses(observation));
        Assert.Equal(2, provider.PeakConcurrency);
    }

    [Fact]
    public async Task ParallelForeachRejectsConditionalRequestAtRuntimeAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(requestApproval: true);
        string yaml = CreateWorkflowYaml(
            items: "=[\"a\"]",
            executionOptions: """
                  mode: Parallel
                  maxParallelism: 2
            """,
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        Assert.Contains(Flatten(error), exception => exception.Message.Contains("checkpoint", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(observation.Events, workflowEvent => workflowEvent is RequestInfoEvent);
    }

    private static readonly string[] s_orderedResponses = ["0:a", "1:b", "2:c", "3:d"];

    private static readonly TimeSpan s_barrierTimeout = TimeSpan.FromSeconds(5);

    private const string InvokeAgentAction = """
                    - kind: InvokeAzureAgent
                      id: invoke_agent
                      agent:
                        name: TestAgent
                      input:
                        arguments:
                          value: =Local.Item
                          index: =Local.Index
                      output:
                        autoSend: true
            """;

    private static string CreateWorkflowYaml(
        string items,
        string? executionOptions,
        string bodyActions,
        string? afterActions = null,
        string? beforeActions = null) =>
        $$"""
        kind: Workflow
        trigger:
          kind: OnConversationStart
          id: workflow
          actions:
        {{beforeActions}}
            - kind: Foreach
              id: parallel_loop
              items: {{items}}
              value: Local.Item
              index: Local.Index
        {{executionOptions}}
              actions:
        {{bodyActions}}
        {{afterActions}}
        """;

    private static Workflow BuildWorkflow(string yaml, ResponseAgentProvider provider)
    {
        using StringReader reader = new(yaml);
        return DeclarativeWorkflowBuilder.Build<string>(reader, new DeclarativeWorkflowOptions(provider));
    }

    private static async Task<WorkflowObservation> RunWorkflowAsync(string yaml, ResponseAgentProvider provider)
    {
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(10));
        Workflow workflow = BuildWorkflow(yaml, provider);
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "input", cancellationToken: timeout.Token).ConfigureAwait(false);
        WorkflowEvent[] events = await CollectEventsAsync(run, timeout.Token).ConfigureAwait(false);
        RunStatus status = await run.GetStatusAsync(timeout.Token).ConfigureAwait(false);
        return new(events, status);
    }

    private static async Task<WorkflowEvent[]> CollectEventsAsync(StreamingRun run, CancellationToken cancellationToken = default)
    {
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent workflowEvent in run.WatchStreamAsync(cancellationToken).ConfigureAwait(false))
        {
            events.Add(workflowEvent);
        }

        return [.. events];
    }

    private static void AssertNoWorkflowError(WorkflowObservation observation)
    {
        Assert.DoesNotContain(observation.Events, workflowEvent => workflowEvent is WorkflowErrorEvent);
        Assert.Equal(RunStatus.Idle, observation.Status);
    }

    private static Exception AssertWorkflowError(WorkflowObservation observation) =>
        Assert.IsAssignableFrom<Exception>(Assert.Single(observation.Events.OfType<WorkflowErrorEvent>()).Data);

    private static string[] GetAgentResponses(WorkflowObservation observation) =>
        [.. observation.Events
            .OfType<AgentResponseEvent>()
            .Where(evt => evt.ExecutorId == "invoke_agent")
            .Select(evt => evt.Response.Messages.Single().Text)];

    private static IEnumerable<Exception> Flatten(Exception exception)
    {
        yield return exception;

        if (exception is AggregateException aggregateException)
        {
            foreach (Exception innerException in aggregateException.InnerExceptions.SelectMany(Flatten))
            {
                yield return innerException;
            }
        }
        else if (exception.InnerException is not null)
        {
            foreach (Exception innerException in Flatten(exception.InnerException))
            {
                yield return innerException;
            }
        }
    }

    private static async Task AwaitWithTimeoutAsync(Task task, TimeSpan timeout)
    {
        Task completedTask = await Task.WhenAny(task, Task.Delay(timeout)).ConfigureAwait(false);
        Assert.Same(task, completedTask);
        await task.ConfigureAwait(false);
    }

    private static async Task<T> AwaitWithTimeoutAsync<T>(Task<T> task, TimeSpan timeout)
    {
        await AwaitWithTimeoutAsync((Task)task, timeout).ConfigureAwait(false);
        return await task.ConfigureAwait(false);
    }

    private sealed record WorkflowObservation(WorkflowEvent[] Events, RunStatus Status);

    private sealed record Invocation(int Index, string Value);

    private sealed class ControlledAgentProvider : ResponseAgentProvider
    {
        private readonly TaskCompletionSource<bool> _barrier = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> _cancellationObserved = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> _firstInvocationStarted = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> _failureBarrier = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<bool> _noActiveInvocations = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly int _barrierParticipants;
        private readonly TimeSpan _barrierTimeout;
        private readonly Func<int, TimeSpan>? _delayByIndex;
        private readonly HashSet<int> _failureIndexes;
        private readonly int _failureBarrierParticipants;
        private readonly HashSet<int> _waitUntilCanceledIndexes;
        private readonly bool _waitUntilCanceled;
        private readonly bool _requestApproval;
        private readonly TimeSpan _conversationWriteDelay;
        private readonly bool _mutateConversationWrites;
        private int _activeCount;
        private int _activeConversationWrites;
        private int _barrierArrivals;
        private int _completedInvocations;
        private int _failureBarrierArrivals;
        private int _invocationCompletionsAtFirstConversationWrite = -1;
        private int _invocationCount;
        private int _peakConcurrency;
        private int _peakConversationWriteConcurrency;

        public ControlledAgentProvider(
            int barrierParticipants = 1,
            TimeSpan? barrierTimeout = null,
            Func<int, TimeSpan>? delayByIndex = null,
            IEnumerable<int>? failureIndexes = null,
            IEnumerable<int>? waitUntilCanceledIndexes = null,
            bool waitUntilCanceled = false,
            bool requestApproval = false,
            TimeSpan? conversationWriteDelay = null,
            int failureBarrierParticipants = 0,
            bool mutateConversationWrites = false)
        {
            this._barrierParticipants = barrierParticipants;
            this._barrierTimeout = barrierTimeout ?? TimeSpan.Zero;
            this._delayByIndex = delayByIndex;
            this._failureIndexes = failureIndexes is null ? [] : [.. failureIndexes];
            this._failureBarrierParticipants = failureBarrierParticipants;
            this._waitUntilCanceledIndexes = waitUntilCanceledIndexes is null ? [] : [.. waitUntilCanceledIndexes];
            this._waitUntilCanceled = waitUntilCanceled;
            this._requestApproval = requestApproval;
            this._conversationWriteDelay = conversationWriteDelay ?? TimeSpan.Zero;
            this._mutateConversationWrites = mutateConversationWrites;
        }

        public int InvocationCount => Volatile.Read(ref this._invocationCount);

        public int PeakConcurrency => Volatile.Read(ref this._peakConcurrency);

        public int PeakConversationWriteConcurrency => Volatile.Read(ref this._peakConversationWriteConcurrency);

        public int InvocationCompletionsAtFirstConversationWrite => Volatile.Read(ref this._invocationCompletionsAtFirstConversationWrite);

        public int ActiveCount => Volatile.Read(ref this._activeCount);

        public ConcurrentBag<Invocation> Invocations { get; } = [];

        public ConcurrentQueue<int> Completions { get; } = [];

        public ConcurrentQueue<string> WorkflowConversationWrites { get; } = [];

        public string? WorkflowConversationId { get; private set; }

        public Task CancellationObserved => this._cancellationObserved.Task;

        public Task FirstInvocationStarted => this._firstInvocationStarted.Task;

        public Task NoActiveInvocations => this._noActiveInvocations.Task;

        public override Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
        {
            this.WorkflowConversationId = Guid.NewGuid().ToString("N");
            return Task.FromResult(this.WorkflowConversationId);
        }

        public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
        {
            if (string.Equals(conversationId, this.WorkflowConversationId, StringComparison.Ordinal)
                && conversationMessage.Text.IndexOf(':') >= 0)
            {
                int active = Interlocked.Increment(ref this._activeConversationWrites);
                UpdatePeak(ref this._peakConversationWriteConcurrency, active);
                Interlocked.CompareExchange(
                    ref this._invocationCompletionsAtFirstConversationWrite,
                    Volatile.Read(ref this._completedInvocations),
                    -1);
                try
                {
                    if (this._conversationWriteDelay > TimeSpan.Zero)
                    {
                        await Task.Delay(this._conversationWriteDelay, cancellationToken).ConfigureAwait(false);
                    }

                    string originalText = conversationMessage.Text;
                    this.WorkflowConversationWrites.Enqueue(originalText);
                    if (this._mutateConversationWrites)
                    {
                        conversationMessage.Contents.Clear();
                        conversationMessage.Contents.Add(new TextContent("mutated"));
                    }
                }
                finally
                {
                    Interlocked.Decrement(ref this._activeConversationWrites);
                }
            }

            return conversationMessage;
        }

        public override Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public override async IAsyncEnumerable<AgentResponseUpdate> InvokeAgentAsync(
            string agentId,
            string? agentVersion,
            string? conversationId,
            IEnumerable<ChatMessage>? messages,
            IDictionary<string, object?>? inputArguments,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            int index = Convert.ToInt32(inputArguments!["index"], CultureInfo.InvariantCulture);
            string value = Convert.ToString(inputArguments["value"], CultureInfo.InvariantCulture)!;
            this.Invocations.Add(new(index, value));
            Interlocked.Increment(ref this._invocationCount);
            this._firstInvocationStarted.TrySetResult(true);

            int activeCount = Interlocked.Increment(ref this._activeCount);
            UpdatePeak(ref this._peakConcurrency, activeCount);
            using CancellationTokenRegistration registration = cancellationToken.Register(() => this._cancellationObserved.TrySetResult(true));

            try
            {
                if (Interlocked.Increment(ref this._barrierArrivals) == this._barrierParticipants)
                {
                    this._barrier.TrySetResult(true);
                }

                if (this._barrierParticipants > 1)
                {
                    await Task.WhenAny(this._barrier.Task, Task.Delay(this._barrierTimeout, cancellationToken)).ConfigureAwait(false);
                    cancellationToken.ThrowIfCancellationRequested();
                }

                if (this._waitUntilCanceled || this._waitUntilCanceledIndexes.Contains(index))
                {
                    await Task.Delay(Timeout.Infinite, cancellationToken).ConfigureAwait(false);
                }

                if (this._delayByIndex is not null)
                {
                    await Task.Delay(this._delayByIndex(index), cancellationToken).ConfigureAwait(false);
                }

                if (this._failureIndexes.Contains(index))
                {
                    if (this._failureBarrierParticipants > 0)
                    {
                        int arrivals = Interlocked.Increment(ref this._failureBarrierArrivals);
                        if (arrivals == this._failureBarrierParticipants)
                        {
                            this._failureBarrier.TrySetResult(true);
                        }

                        await this._failureBarrier.Task.ConfigureAwait(false);
                    }

                    throw new InvalidOperationException($"Failure for iteration {index}.");
                }

                this.Completions.Enqueue(index);
                Interlocked.Increment(ref this._completedInvocations);

                if (this._requestApproval)
                {
                    yield return new AgentResponseUpdate(
                        ChatRole.Assistant,
                        [new ToolApprovalRequestContent("approval", new FunctionCallContent("approval", "test"))]);
                }
                else
                {
                    yield return new AgentResponseUpdate(ChatRole.Assistant, $"{index}:{value}");
                }
            }
            finally
            {
                if (cancellationToken.IsCancellationRequested)
                {
                    this._cancellationObserved.TrySetResult(true);
                }

                if (Interlocked.Decrement(ref this._activeCount) == 0)
                {
                    this._noActiveInvocations.TrySetResult(true);
                }
            }
        }

        public override async IAsyncEnumerable<ChatMessage> GetMessagesAsync(
            string conversationId,
            int? limit = null,
            string? after = null,
            string? before = null,
            bool newestFirst = false,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask.ConfigureAwait(false);
            yield break;
        }

        private static void UpdatePeak(ref int peak, int candidate)
        {
            int observed;
            do
            {
                observed = Volatile.Read(ref peak);
                if (candidate <= observed)
                {
                    return;
                }
            }
            while (Interlocked.CompareExchange(ref peak, candidate, observed) != observed);
        }
    }
}
