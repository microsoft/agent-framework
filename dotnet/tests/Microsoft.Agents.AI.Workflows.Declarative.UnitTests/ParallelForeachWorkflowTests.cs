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
    public async Task ParallelForeachIsolatesStateAndCommitsInSourceOrderAsync()
    {
        // Arrange
        ControlledAgentProvider provider = new(delayByIndex: index => TimeSpan.FromMilliseconds((3 - index) * 30));
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
        Assert.Equal(
            s_orderedResponses,
            provider.Invocations.OrderBy(invocation => invocation.Index).Select(invocation => $"{invocation.Index}:{invocation.Value}"));
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
            bodyActions: InvokeAgentAction);

        // Act
        WorkflowObservation observation = await RunWorkflowAsync(yaml, provider);

        // Assert
        Exception error = AssertWorkflowError(observation);
        Assert.Contains(Flatten(error), exception => exception is AggregateException);
        Assert.Contains(Flatten(error), exception => exception.Message.Contains("iteration 1", StringComparison.OrdinalIgnoreCase));
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
        Assert.DoesNotContain(events.OfType<DeclarativeActionCompletedEvent>(), evt => evt.ActionId == "parallel_loop");
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

    [Theory]
    [InlineData("Parallel", 0)]
    [InlineData("Parallel", -1)]
    [InlineData("unsupported", 2)]
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
        private readonly int _barrierParticipants;
        private readonly TimeSpan _barrierTimeout;
        private readonly Func<int, TimeSpan>? _delayByIndex;
        private readonly HashSet<int> _failureIndexes;
        private readonly bool _waitUntilCanceled;
        private readonly bool _requestApproval;
        private int _activeCount;
        private int _barrierArrivals;
        private int _invocationCount;
        private int _peakConcurrency;

        public ControlledAgentProvider(
            int barrierParticipants = 1,
            TimeSpan? barrierTimeout = null,
            Func<int, TimeSpan>? delayByIndex = null,
            IEnumerable<int>? failureIndexes = null,
            bool waitUntilCanceled = false,
            bool requestApproval = false)
        {
            this._barrierParticipants = barrierParticipants;
            this._barrierTimeout = barrierTimeout ?? TimeSpan.Zero;
            this._delayByIndex = delayByIndex;
            this._failureIndexes = failureIndexes is null ? [] : [.. failureIndexes];
            this._waitUntilCanceled = waitUntilCanceled;
            this._requestApproval = requestApproval;
        }

        public int InvocationCount => Volatile.Read(ref this._invocationCount);

        public int PeakConcurrency => Volatile.Read(ref this._peakConcurrency);

        public ConcurrentBag<Invocation> Invocations { get; } = [];

        public Task CancellationObserved => this._cancellationObserved.Task;

        public Task FirstInvocationStarted => this._firstInvocationStarted.Task;

        public override Task<string> CreateConversationAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult(Guid.NewGuid().ToString("N"));

        public override Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default) =>
            Task.FromResult(conversationMessage);

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

                if (this._waitUntilCanceled)
                {
                    await Task.Delay(Timeout.Infinite, cancellationToken).ConfigureAwait(false);
                }

                if (this._delayByIndex is not null)
                {
                    await Task.Delay(this._delayByIndex(index), cancellationToken).ConfigureAwait(false);
                }

                if (this._failureIndexes.Contains(index))
                {
                    throw new InvalidOperationException($"Failure for iteration {index}.");
                }

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

                Interlocked.Decrement(ref this._activeCount);
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
