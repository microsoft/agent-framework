// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
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
        status.Should().Be(RunStatus.Idle, "workflow should complete execution");

        // The run should have events (at minimum, a WorkflowOutputEvent)
        run.OutgoingEvents.Should().NotBeEmpty("workflow should produce events during execution");

        // Check that we have an agent execution event
        var agentEvents = run.OutgoingEvents.OfType<AgentRunUpdateEvent>().ToList();
        agentEvents.Should().NotBeEmpty("agent should have executed and produced update events");

        // Check that we have output events
        var outputEvents = run.OutgoingEvents.OfType<WorkflowOutputEvent>().ToList();
        outputEvents.Should().NotBeEmpty("workflow should produce output events");
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
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new List<ChatMessage> { inputMessage });

        // Send TurnToken to actually trigger execution (this is the key step)
        bool messageSent = await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        messageSent.Should().BeTrue("TurnToken should be accepted");

        // Collect events
        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert: The workflow should have executed and produced events
        RunStatus status = await run.GetStatusAsync();
        status.Should().Be(RunStatus.Idle, "workflow should complete execution");

        events.Should().NotBeEmpty("workflow should produce events during execution");

        // Check that we have agent execution events
        var agentEvents = events.OfType<AgentRunUpdateEvent>().ToList();
        agentEvents.Should().NotBeEmpty("agent should have executed and produced update events");

        // Check that we have output events
        var outputEvents = events.OfType<WorkflowOutputEvent>().ToList();
        outputEvents.Should().NotBeEmpty("workflow should produce output events");
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
        await using StreamingRun streamingRun = await InProcessExecution.StreamAsync(workflow2, new List<ChatMessage> { inputMessage });
        await streamingRun.TrySendMessageAsync(new TurnToken(emitEvents: true));

        List<WorkflowEvent> streamingEvents = [];
        await foreach (WorkflowEvent evt in streamingRun.WatchStreamAsync())
        {
            streamingEvents.Add(evt);
        }

        // Assert: Both should have produced events
        // The streaming version works (we know this from the issue report)
        streamingEvents.Should().NotBeEmpty("streaming version should produce events");

        // The non-streaming version should also produce events (this is the bug being tested)
        nonStreamingEvents.Should().NotBeEmpty("non-streaming version should also produce events");

        // Both should have similar types of events
        var streamingAgentEvents = streamingEvents.OfType<AgentRunUpdateEvent>().Count();
        var nonStreamingAgentEvents = nonStreamingEvents.OfType<AgentRunUpdateEvent>().Count();

        nonStreamingAgentEvents.Should().Be(streamingAgentEvents,
            "both versions should produce the same number of agent events");
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

        public override AgentThread GetNewThread() => new SimpleTestAgentThread();

        public override AgentThread DeserializeThread(System.Text.Json.JsonElement serializedThread,
            System.Text.Json.JsonSerializerOptions? jsonSerializerOptions = null) => new SimpleTestAgentThread();

        public override Task<AgentRunResponse> RunAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            var lastMessage = messages.LastOrDefault();
            var responseMessage = new ChatMessage(ChatRole.Assistant, $"Echo: {lastMessage?.Text ?? "no message"}");
            return Task.FromResult(new AgentRunResponse(responseMessage));
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentThread? thread = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            var lastMessage = messages.LastOrDefault();
            var responseText = $"Echo: {lastMessage?.Text ?? "no message"}";

            string messageId = Guid.NewGuid().ToString("N");

            // Yield role first
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, this.Name)
            {
                AuthorName = this.Name,
                MessageId = messageId
            };

            // Then yield content
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, responseText)
            {
                AuthorName = this.Name,
                MessageId = messageId
            };
        }
    }

    /// <summary>
    /// Simple thread implementation for SimpleTestAgent.
    /// </summary>
    private sealed class SimpleTestAgentThread : InMemoryAgentThread;
}
