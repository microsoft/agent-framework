// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for InProcessExecution to verify streaming and non-streaming execution behavior.
/// </summary>
public class InProcessExecutionTests
{
    [Fact]
    public async Task ConcurrentExecutionRejectsDirectNonShareableExecutorAsync()
    {
        // Arrange
        FunctionExecutor<int> executor = new("Function", HandleAsync, declareCrossRunShareable: false);
        Workflow workflow = new WorkflowBuilder(executor.BindExecutor()).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, executor.Id, expectedConcurrent: false);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Fact]
    public async Task ConcurrentExecutionRejectsNonThreadsafeFunctionBindingAsync()
    {
        // Arrange
        Func<int, IWorkflowContext, CancellationToken, ValueTask> handler = HandleAsync;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: false);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, expectedConcurrent: false);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Fact]
    public async Task ConcurrentExecutionAcceptsThreadsafeInputOnlyFunctionBindingAsync()
    {
        // Arrange
        Func<int, IWorkflowContext, CancellationToken, ValueTask> handler = HandleAsync;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: true);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, expectedConcurrent: true);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Fact]
    public async Task ThreadsafeFunctionHandlerExceptionUsesWorkflowErrorPathAsync()
    {
        // Arrange
        InvalidOperationException expected = new("Handler failed.");
        Func<int, IWorkflowContext, CancellationToken, ValueTask> handler = (_, _, _) => throw expected;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: true);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act
        await using Run run = await InProcessExecution.Concurrent.RunAsync(workflow, 42);

        // Assert
        WorkflowErrorEvent error = Assert.Single(run.OutgoingEvents.OfType<WorkflowErrorEvent>());
        Assert.Same(expected, error.Exception?.GetBaseException());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ConcurrentExecutionHonorsOutputFunctionThreadSafetyAsync(bool threadsafe)
    {
        // Arrange
        Func<int, int> handler = static value => value;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: threadsafe);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, threadsafe);
    }

    [Fact]
    public async Task ConcurrentExecutionRejectsFunctionBindingWithDefaultThreadSafetyAsync()
    {
        // Arrange
        Func<int, int> handler = static value => value;
        ExecutorBinding binding = handler.BindAsExecutor("Function");
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, expectedConcurrent: false);
    }

    [Fact]
    public async Task OffThreadExecutionAllowsSequentialReuseOfNonThreadsafeFunctionBindingAsync()
    {
        // Arrange
        List<int> handledMessages = [];
        Func<int, IWorkflowContext, CancellationToken, ValueTask> handler = HandleAsync;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: false);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act
        await using (Run firstRun = await InProcessExecution.OffThread.RunAsync(workflow, 1))
        {
            Assert.Empty(firstRun.OutgoingEvents.OfType<WorkflowErrorEvent>());
        }

        await using (Run secondRun = await InProcessExecution.OffThread.RunAsync(workflow, 2))
        {
            Assert.Empty(secondRun.OutgoingEvents.OfType<WorkflowErrorEvent>());
        }

        // Assert
        Assert.Equal([1, 2], handledMessages);

        ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken)
        {
            handledMessages.Add(message);
            return default;
        }
    }

    [Fact]
    public async Task ConcurrentExecutionAcceptsFactoryCreatedExecutorAsync()
    {
        // Arrange
        Func<string, string, ValueTask<FunctionExecutor<int>>> factory =
            (id, _) => new(new FunctionExecutor<int>(id, HandleAsync, declareCrossRunShareable: false));
        ExecutorBinding binding = factory.BindExecutor();
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act
        Executor first = await binding.CreateInstanceAsync("session-a");
        Executor second = await binding.CreateInstanceAsync("session-b");

        // Assert
        Assert.NotSame(first, second);
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, expectedConcurrent: true);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AggregatingFunctionBindingPreservesThreadSafetyAsync(bool threadsafe)
    {
        // Arrange
        Func<int, int, int> aggregator = static (accumulation, value) => accumulation + value;
        ExecutorBinding binding = aggregator.BindAsExecutor("Aggregator", threadsafe: threadsafe);
        Workflow workflow = new WorkflowBuilder(binding).Build();

        // Act & Assert
        await AssertConcurrentEligibilityAsync(workflow, binding.Id, threadsafe);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SubworkflowBindingPropagatesDirectExecutorConcurrencyCapabilityAsync(bool crossRunShareable)
    {
        // Arrange
        FunctionExecutor<int> executor = new("Function", HandleAsync, declareCrossRunShareable: crossRunShareable);
        Workflow child = new WorkflowBuilder(executor.BindExecutor()).Build();
        ExecutorBinding childBinding = child.BindAsExecutor("ChildWorkflow");

        // Act
        Workflow parent = new WorkflowBuilder(childBinding).Build();

        // Assert
        Assert.Equal(crossRunShareable, child.AllowConcurrent);
        Assert.Equal(crossRunShareable, childBinding.SupportsConcurrentSharedExecution);
        Assert.Equal(crossRunShareable, parent.AllowConcurrent);
        await AssertConcurrentEligibilityAsync(parent, childBinding.Id, crossRunShareable);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Fact]
    public void SubworkflowConcurrencyCapabilityPropagatesTransitively()
    {
        // Arrange
        FunctionExecutor<int> executor = new("Function", HandleAsync, declareCrossRunShareable: false);
        Workflow grandchild = new WorkflowBuilder(executor.BindExecutor()).Build();
        ExecutorBinding grandchildBinding = grandchild.BindAsExecutor("GrandchildWorkflow");
        Workflow child = new WorkflowBuilder(grandchildBinding).Build();
        ExecutorBinding childBinding = child.BindAsExecutor("ChildWorkflow");

        // Act
        Workflow parent = new WorkflowBuilder(childBinding).Build();

        // Assert
        Assert.False(grandchild.AllowConcurrent);
        Assert.False(child.AllowConcurrent);
        Assert.False(parent.AllowConcurrent);

        static ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken) => default;
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task WorkflowHostAgentUsesWorkflowConcurrencyCapabilityForDefaultEnvironmentAsync(bool threadsafe, bool nested)
    {
        // Arrange
        bool? concurrentRunsEnabled = null;
        Workflow workflow = CreateChatFunctionWorkflow(threadsafe, value => concurrentRunsEnabled = value);
        if (nested)
        {
            ExecutorBinding childBinding = workflow.BindAsExecutor("ChildWorkflow");
            workflow = new WorkflowBuilder(childBinding).WithOutputFrom(childBinding).Build();
        }

        AIAgent agent = workflow.AsAIAgent();

        // Act
        _ = await agent.RunAsync(new ChatMessage(ChatRole.User, "Hello"));

        // Assert
        Assert.Equal(threadsafe, concurrentRunsEnabled);
    }

    private static async Task AssertConcurrentEligibilityAsync(Workflow workflow, string executorId, bool expectedConcurrent)
    {
        if (expectedConcurrent)
        {
            await using StreamingRun run = await InProcessExecution.Concurrent.OpenStreamingAsync(workflow);
            Assert.NotNull(run);
        }
        else
        {
            InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
                () => InProcessExecution.Concurrent.OpenStreamingAsync(workflow).AsTask());
            Assert.Contains(executorId, exception.Message);
        }
    }

    private static Workflow CreateChatFunctionWorkflow(bool threadsafe, Action<bool> observeConcurrentRuns)
    {
        ExecutorBinding start = new SimpleTestAgent("ChatAgent").BindAsExecutor(emitEvents: false);
        Func<List<ChatMessage>, IWorkflowContext, CancellationToken, ValueTask<ChatMessage>> handler = HandleAsync;
        ExecutorBinding binding = handler.BindAsExecutor("Function", threadsafe: threadsafe);
        return new WorkflowBuilder(start)
            .AddEdge(start, binding)
            .WithOutputFrom(binding)
            .Build();

        ValueTask<ChatMessage> HandleAsync(List<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            observeConcurrentRuns(context.ConcurrentRunsEnabled);
            return new(new ChatMessage(ChatRole.Assistant, "Done"));
        }
    }

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
