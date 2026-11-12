// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for InProcessExecution to verify streaming and non-streaming execution behavior.
/// </summary>
public class InProcessExecutionTests
{
    /// <summary>
    /// The non-streaming version (RunAsync) should execute the workflow and produce events,
    /// similar to the streaming version (StreamAsync + TrySendMessageAsync).
    /// </summary>
    [Fact]
    public async Task RunAsyncShouldExecuteWorkflowAsync()
    {
        // Arrange: Create a simple agent that responds to messages
        var agent = new SimpleTestAgent("test-agent");
        var workflow = AgentWorkflowBuilder.BuildSequential(agent);
        var inputMessage = new ChatMessage(ChatRole.User, "Hello");

        // Act: Execute using non-streaming RunAsync
        Run run = await InProcessExecution.RunAsync(workflow, new List<ChatMessage> { inputMessage });

        // Assert: The workflow should have executed and produced events
        RunStatus status = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        // The run should have events (at minimum, a WorkflowOutputEvent)
        Assert.NotEmpty(run.OutgoingEvents);

        // Check that we have an agent execution event
        var agentEvents = run.OutgoingEvents.OfType<AgentResponseUpdateEvent>().ToList();
        Assert.NotEmpty(agentEvents);

        // Check that we have output events
        var outputEvents = run.OutgoingEvents.OfType<WorkflowOutputEvent>().ToList();
        Assert.NotEmpty(outputEvents);
    }

    /// <summary>
    /// This test shows that the streaming version works correctly when TurnToken is sent following a message.
    /// </summary>
    [Fact]
    public async Task StreamAsyncWithTurnTokenShouldExecuteWorkflowAsync()
    {
        // Arrange: Create a simple agent that responds to messages
        var agent = new SimpleTestAgent("test-agent");
        var workflow = AgentWorkflowBuilder.BuildSequential(agent);
        var inputMessage = new ChatMessage(ChatRole.User, "Hello");

        // Act: Execute using streaming version with TurnToken
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, new List<ChatMessage> { inputMessage });

        // Send TurnToken to actually trigger execution (this is the key step)
        bool messageSent = await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        Assert.True(messageSent);

        // Collect events
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert: The workflow should have executed and produced events
        RunStatus status = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        Assert.NotEmpty(events);

        // Check that we have agent execution events
        var agentEvents = events.OfType<AgentResponseUpdateEvent>().ToList();
        Assert.NotEmpty(agentEvents);

        // Check that we have output events
        var outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        Assert.NotEmpty(outputEvents);
    }

    /// <summary>
    /// This test compares the behavior of RunAsync vs StreamAsync to highlight the difference.
    /// Both should produce similar results, but as of issue #1315, RunAsync fails to execute.
    /// </summary>
    [Fact]
    public async Task RunAsyncAndStreamAsyncShouldProduceSimilarResultsAsync()
    {
        // Arrange: Create the same workflow for both tests
        var agent1 = new SimpleTestAgent("test-agent-1");
        var workflow1 = AgentWorkflowBuilder.BuildSequential(agent1);

        var agent2 = new SimpleTestAgent("test-agent-2");
        var workflow2 = AgentWorkflowBuilder.BuildSequential(agent2);

        var inputMessage = new ChatMessage(ChatRole.User, "Test message");

        // Act 1: Execute using RunAsync (non-streaming)
        Run nonStreamingRun = await InProcessExecution.RunAsync(workflow1, new List<ChatMessage> { inputMessage });
        var nonStreamingEvents = nonStreamingRun.OutgoingEvents.ToList();

        // Act 2: Execute using StreamAsync (streaming) with TurnToken
        await using StreamingRun streamingRun = await InProcessExecution.RunStreamingAsync(workflow2, new List<ChatMessage> { inputMessage });
        await streamingRun.TrySendMessageAsync(new TurnToken(emitEvents: true));

        List<WorkflowEvent> streamingEvents = [];
        await foreach (WorkflowEvent evt in streamingRun.WatchStreamAsync())
        {
            streamingEvents.Add(evt);
        }

        // Assert: Both should have produced events
        // The streaming version works (we know this from the issue report)
        Assert.NotEmpty(streamingEvents);

        // The non-streaming version should also produce events (this is the bug being tested)
        Assert.NotEmpty(nonStreamingEvents);

        // Both should have similar types of events
        var streamingAgentEvents = streamingEvents.OfType<AgentResponseUpdateEvent>().Count();
        var nonStreamingAgentEvents = nonStreamingEvents.OfType<AgentResponseUpdateEvent>().Count();

        Assert.Equal(streamingAgentEvents, nonStreamingAgentEvents);
    }

    /// <summary>
    /// This test checks that the logic around waiting for input and halting appropriately works right when the
    /// workflow runs to halting before the EventStream is watched by the user.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsyncWaitToTakeStreamAsync()
    {
        // Arrange: Create a simple agent that responds to messages
        var agent = new SimpleTestAgent("test-agent");
        var workflow = AgentWorkflowBuilder.BuildSequential(agent);
        var inputMessage = new ChatMessage(ChatRole.User, "Hello");

        // Act: Execute using streaming version with TurnToken
        await using StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, new List<ChatMessage> { inputMessage });

        // Send TurnToken to actually trigger execution (this is the key step)
        bool messageSent = await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        Assert.True(messageSent);

        while (await run.GetStatusAsync() != RunStatus.Idle)
        {
            await Task.Delay(200);
        }

        // Collect events
        List<WorkflowEvent> events = [];

        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert: The workflow should have executed and produced events
        RunStatus status = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        Assert.NotEmpty(events);

        // Check that we have agent execution events
        var agentEvents = events.OfType<AgentResponseUpdateEvent>().ToList();
        Assert.NotEmpty(agentEvents);

        // Check that we have output events
        var outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        Assert.NotEmpty(outputEvents);
    }

    /// <summary>
    /// An executor that fails to initialize must not leave the workflow owned by the failed run, so the same
    /// workflow can run again once initialization succeeds.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task RunAsync_ReleasesWorkflowAfterExecutorInitializationFailsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();
        ForwardMessageExecutor<string> start = new("start");
        FlakyExecutor<string> target = new("target", FlakyStep.Initialization);
        Workflow workflow = new WorkflowBuilder(start).AddEdge(start, target).WithOutputFrom(target).Build();

        // Act
        Run failedRun = await env.RunAsync(workflow, "first");
        await failedRun.DisposeAsync();
        await using Run run = await env.RunAsync(workflow, "second");

        // Assert
        Assert.Contains(failedRun.OutgoingEvents, evt => evt is ExecutorFailedEvent { Data: TimeoutException });
        Assert.Equal(["second"], run.OutgoingEvents.OfType<WorkflowOutputEvent>().Select(evt => evt.Data));
    }

    /// <summary>
    /// Disposing a run while an executor is still initializing cancels the initialization, which must not leave
    /// the workflow owned by the abandoned run.
    /// </summary>
    [Fact]
    public async Task StreamingRun_ReleasesWorkflowWhenDisposedDuringExecutorInitializationAsync()
    {
        // Arrange
        TokenForwardingExecutor start = new("start");
        FlakyExecutor<string> target = new("target", FlakyStep.InitializationUntilCancelled);
        Workflow workflow = new WorkflowBuilder(start).AddEdge(start, target).WithOutputFrom(target).Build();

        // Act
        StreamingRun abandonedRun = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "first");
        Task initializing = target.FirstInitializationStarted.Task;
        Assert.Same(initializing, await Task.WhenAny(initializing, Task.Delay(TimeSpan.FromSeconds(10))));
        await abandonedRun.DisposeAsync();
        await using StreamingRun run = await InProcessExecution.OffThread.RunStreamingAsync(workflow, "second");

        // Assert
        Assert.Equal(["second"], await CollectOutputsAsync(run));
    }

    /// <summary>
    /// A run whose executor fails to dispose reports that failure, but must still release the workflow.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task RunAsync_ReleasesWorkflowAfterExecutorDisposalFailsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();
        FlakyExecutor<string> start = new("start", FlakyStep.Disposal);
        Workflow workflow = new WorkflowBuilder(start).WithOutputFrom(start).Build();

        // Act
        Run failedRun = await env.RunAsync(workflow, "first");
        await Assert.ThrowsAsync<InvalidOperationException>(() => failedRun.DisposeAsync().AsTask());
        await using Run run = await env.RunAsync(workflow, "second");

        // Assert
        Assert.Equal(["second"], run.OutgoingEvents.OfType<WorkflowOutputEvent>().Select(evt => evt.Data));
    }

    /// <summary>
    /// When the start executor fails to initialize while the first input is enqueued, the caller never receives
    /// the run, so the run must be ended before the error propagates.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task RunStreamingAsync_ReleasesWorkflowAfterStartExecutorInitializationFailsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();
        FlakyExecutor<string> start = new("start", FlakyStep.Initialization);
        Workflow workflow = new WorkflowBuilder(start).WithOutputFrom(start).Build();

        // Act
        await Assert.ThrowsAsync<TimeoutException>(() => env.RunStreamingAsync(workflow, "first").AsTask());
        await using StreamingRun run = await env.RunStreamingAsync(workflow, "second");

        // Assert
        Assert.Equal(["second"], await CollectOutputsAsync(run));
    }

    /// <summary>
    /// <see cref="InProcessExecutionEnvironment.RunAsync{TInput}(Workflow, TInput, string?, CancellationToken)"/> only
    /// creates the start executor while enqueueing when the input type is not one of its declared input types; a
    /// failure there must also end the run before the error propagates.
    /// </summary>
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    internal async Task RunAsync_ReleasesWorkflowAfterStartExecutorInitializationFailsAsync(ExecutionEnvironment environment)
    {
        // Arrange
        InProcessExecutionEnvironment env = environment.ToWorkflowExecutionEnvironment();
        FlakyExecutor<object> start = new("start", FlakyStep.Initialization);
        Workflow workflow = new WorkflowBuilder(start).WithOutputFrom(start).Build();

        // Act
        await Assert.ThrowsAsync<TimeoutException>(() => env.RunAsync(workflow, "first").AsTask());
        await using Run run = await env.RunAsync(workflow, "second");

        // Assert
        Assert.Equal(["second"], run.OutgoingEvents.OfType<WorkflowOutputEvent>().Select(evt => evt.Data));
    }

    private static async Task<List<object?>> CollectOutputsAsync(StreamingRun run)
    {
        List<object?> outputs = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is WorkflowOutputEvent output)
            {
                outputs.Add(output.Data);
            }
        }

        return outputs;
    }

    /// <summary>
    /// Forwards every message with the handler's cancellation token, which is also the token the target executor
    /// is initialized with when this send creates it.
    /// </summary>
    private sealed class TokenForwardingExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            protocolBuilder.RouteBuilder.AddHandler<string>(
                (message, context, cancellationToken) => context.SendMessageAsync(message, cancellationToken: cancellationToken));

            return protocolBuilder.SendsMessage<string>();
        }
    }

    private enum FlakyStep
    {
        /// <summary>The first initialization throws.</summary>
        Initialization,

        /// <summary>The first initialization waits until it is cancelled.</summary>
        InitializationUntilCancelled,

        /// <summary>The first disposal throws.</summary>
        Disposal,
    }

    /// <summary>
    /// Yields every message it receives. The first attempt at the given <see cref="FlakyStep"/> fails.
    /// </summary>
    private sealed class FlakyExecutor<TMessage>(string id, FlakyStep flakyStep) : Executor(id), IAsyncDisposable where TMessage : notnull
    {
        private int _initializations;
        private int _disposals;

        public TaskCompletionSource<bool> FirstInitializationStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        protected internal override async ValueTask InitializeAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            if (Interlocked.Increment(ref this._initializations) > 1)
            {
                return;
            }

            this.FirstInitializationStarted.TrySetResult(true);
            if (flakyStep == FlakyStep.Initialization)
            {
                throw new TimeoutException("Connecting to the backend timed out.");
            }

            if (flakyStep == FlakyStep.InitializationUntilCancelled)
            {
                await Task.Delay(Timeout.Infinite, cancellationToken);
            }
        }

        public ValueTask DisposeAsync()
        {
            if (flakyStep == FlakyStep.Disposal && Interlocked.Increment(ref this._disposals) == 1)
            {
                throw new InvalidOperationException("Closing the backend connection failed.");
            }

            return default;
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
        {
            protocolBuilder.RouteBuilder.AddHandler<TMessage>((message, context) => context.YieldOutputAsync(message));

            return protocolBuilder.YieldsOutput<TMessage>();
        }
    }

    /// <summary>
    /// Simple test agent that echoes back the input message.
    /// </summary>
    private sealed class SimpleTestAgent : AIAgent
    {
        public SimpleTestAgent(string name)
        {
            this.Name = name;
        }

        public override string Name { get; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) => new(new SimpleTestAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(System.Text.Json.JsonElement serializedState,
            System.Text.Json.JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => new(new SimpleTestAgentSession());

        protected override ValueTask<System.Text.Json.JsonElement> SerializeSessionCoreAsync(AgentSession session, System.Text.Json.JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            var lastMessage = messages.LastOrDefault();
            var responseMessage = new ChatMessage(ChatRole.Assistant, $"Echo: {lastMessage?.Text ?? "no message"}");
            return Task.FromResult(new AgentResponse(responseMessage));
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            var lastMessage = messages.LastOrDefault();
            var responseText = $"Echo: {lastMessage?.Text ?? "no message"}";

            string messageId = Guid.NewGuid().ToString("N");

            // Yield role first
            yield return new AgentResponseUpdate(ChatRole.Assistant, this.Name)
            {
                AuthorName = this.Name,
                MessageId = messageId
            };

            // Then yield content
            yield return new AgentResponseUpdate(ChatRole.Assistant, responseText)
            {
                AuthorName = this.Name,
                MessageId = messageId
            };
        }
    }

    /// <summary>
    /// Simple session implementation for SimpleTestAgent.
    /// </summary>
    private sealed class SimpleTestAgentSession : AgentSession;
}
