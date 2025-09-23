// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.Workflows.UnitTests;

public class AgentWorkflowBuilderTests
{
    [Fact]
    public void BuildSequential_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(null!));
        Assert.Throws<ArgumentException>("agents", () => AgentWorkflowBuilder.BuildSequential());
    }

    [Fact]
    public void BuildConcurrent_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildConcurrent(null!));
    }

    [Fact]
    public void BuildHandoffs_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("initialAgent", () => AgentWorkflowBuilder.StartHandoffWith(null!));

        var agent = new DoubleEchoAgent("agent");
        var handoffs = AgentWorkflowBuilder.StartHandoffWith(agent);
        Assert.NotNull(handoffs);

        Assert.Throws<ArgumentNullException>("from", () => handoffs.WithHandoff(null!, new DoubleEchoAgent("a2")));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoff(new DoubleEchoAgent("a2"), (AIAgent)null!));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoff(new DoubleEchoAgent("a2"), null!));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoff(new DoubleEchoAgent("a2"), [null!]));

        var noDescriptionAgent = new ChatClientAgent(new MockChatClient(delegate { return new(); }));
        Assert.Throws<ArgumentException>("to", () => handoffs.WithHandoff(agent, noDescriptionAgent));
    }

    [Fact]
    public async Task BuildSequential_AgentsRunInOrderAsync()
    {
        var workflow = AgentWorkflowBuilder.BuildSequential(
            new DoubleEchoAgent("agent1"),
            new DoubleEchoAgent("agent2"),
            new DoubleEchoAgent("agent3"));

        for (int iter = 0; iter < 3; iter++)
        {
            (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

            const string Expected = "agent1abcabcagent2agent1abcabcagent1abcabcagent3agent2agent1abcabcagent1abcabcagent2agent1abcabcagent1abcabc";
            Assert.Equal(Expected, updateText);

            Assert.NotNull(result);
            Assert.NotNull(Assert.Single(result));
        }
    }

    private class DoubleEchoAgent(string name) : AIAgent
    {
        public override AgentThread GetNewThread()
            => new DoubleEchoAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new DoubleEchoAgentThread();

        public override Task<AgentRunResponse> RunAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            string id = Guid.NewGuid().ToString("N");
            var contents = messages.SelectMany(m => m.Contents).ToList();

            await Task.Yield();

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, name) { MessageId = id };
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, contents) { MessageId = id };
            yield return new AgentRunResponseUpdate(ChatRole.Assistant, contents) { MessageId = id };
        }
    }

    private sealed class DoubleEchoAgentThread() : InMemoryAgentThread();

    [Fact]
    public async Task BuildConcurrent_AgentsRunInParallelAsync()
    {
        StrongBox<TaskCompletionSource<bool>> barrier = new();
        StrongBox<int> remaining = new();

        var workflow = AgentWorkflowBuilder.BuildConcurrent(
        [
            new DoubleEchoAgentWithBarrier("agent1", barrier, remaining),
            new DoubleEchoAgentWithBarrier("agent2", barrier, remaining),
        ]);

        for (int iter = 0; iter < 3; iter++)
        {
            barrier.Value = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            remaining.Value = 2;

            (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

            Assert.Single(Regex.Matches(updateText, "agent1"));
            Assert.Single(Regex.Matches(updateText, "agent2"));
            Assert.NotNull(result);

            // TODO: https://github.com/microsoft/agent-framework/issues/784
            // These asserts are flaky until we guarantee message delivery order.
            //Assert.Equal(4, Regex.Matches(updateText, "abc").Count);
            //Assert.Equal(2, result.Count);
        }
    }

    [Fact]
    public async Task Handoffs_NoTransfers_ResponseServedByOriginalAgentAsync()
    {
        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            ChatMessage message = Assert.Single(messages);
            Assert.Equal("abc", Assert.IsType<TextContent>(Assert.Single(message.Contents)).Text);

            string? endFunctionName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("end", StringComparison.Ordinal))?.Name;
            Assert.NotNull(endFunctionName);

            return new(new ChatMessage(ChatRole.Assistant,
            [
                new TextContent("Hello from agent1"),
                new FunctionCallContent("call12345", endFunctionName),
            ]));
        }));

        var workflow =
            AgentWorkflowBuilder.StartHandoffWith(initialAgent)
            .WithHandoff(initialAgent, new ChatClientAgent(new MockChatClient(delegate
            {
                Assert.Fail("Should never be invoked.");
                return new();
            }), description: "nop"))
            .Build();

        (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.Equal("Hello from agent1", updateText);
        Assert.NotNull(result);

        Assert.Equal(2, result.Count);

        Assert.Equal(ChatRole.User, result[0].Role);
        Assert.Equal("abc", result[0].Text);

        Assert.Equal(ChatRole.Assistant, result[1].Role);
        Assert.Equal("Hello from agent1", result[1].Text);
    }

    [Fact]
    public async Task Handoffs_OneTransfer_ResponseServedBySecondAgentAsync()
    {
        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            ChatMessage message = Assert.Single(messages);
            Assert.Equal("abc", Assert.IsType<TextContent>(Assert.Single(message.Contents)).Text);

            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var nextAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? endFunctionName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("end", StringComparison.Ordinal))?.Name;
            Assert.NotNull(endFunctionName);

            return new(new ChatMessage(ChatRole.Assistant,
            [
                new TextContent("Hello from agent2"),
                new FunctionCallContent("call2", endFunctionName),
            ]));
        }), name: "nextAgent", description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.StartHandoffWith(initialAgent)
            .WithHandoff(initialAgent, nextAgent)
            .Build();

        (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.Equal("Hello from agent2", updateText);
        Assert.NotNull(result);

        Assert.Equal(4, result.Count);

        Assert.Equal(ChatRole.User, result[0].Role);
        Assert.Equal("abc", result[0].Text);

        Assert.Equal(ChatRole.Assistant, result[1].Role);
        Assert.Equal("", result[1].Text);
        Assert.Contains("initialAgent", result[1].AuthorName);

        Assert.Equal(ChatRole.Tool, result[2].Role);
        Assert.Contains("initialAgent", result[2].AuthorName);

        Assert.Equal(ChatRole.Assistant, result[3].Role);
        Assert.Equal("Hello from agent2", result[3].Text);
        Assert.Contains("nextAgent", result[3].AuthorName);
    }

    [Fact]
    public async Task Handoffs_TwoTransfers_ResponseServedByThirdAgentAsync()
    {
        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            ChatMessage message = Assert.Single(messages);
            Assert.Equal("abc", Assert.IsType<TextContent>(Assert.Single(message.Contents)).Text);

            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            // Only a handoff function call.
            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var secondAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            // Second agent should receive the conversation so far (including previous assistant + tool messages eventually).
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call2", transferFuncName)]));
        }), name: "secondAgent", description: "The second agent");

        var thirdAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? endFunctionName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("end", StringComparison.Ordinal))?.Name;
            Assert.NotNull(endFunctionName);

            return new(new ChatMessage(ChatRole.Assistant,
            [
                new TextContent("Hello from agent3"),
                new FunctionCallContent("call3", endFunctionName),
            ]));
        }), name: "thirdAgent", description: "The third / final agent");

        var workflow =
            AgentWorkflowBuilder.StartHandoffWith(initialAgent)
            .WithHandoff(initialAgent, secondAgent)
            .WithHandoff(secondAgent, thirdAgent)
            .Build();

        (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.Equal("Hello from agent3", updateText);
        Assert.NotNull(result);

        // User + (assistant empty + tool) for each of first two agents + final assistant with text.
        Assert.Equal(6, result.Count);

        Assert.Equal(ChatRole.User, result[0].Role);
        Assert.Equal("abc", result[0].Text);

        Assert.Equal(ChatRole.Assistant, result[1].Role);
        Assert.Equal("", result[1].Text);
        Assert.Contains("initialAgent", result[1].AuthorName);

        Assert.Equal(ChatRole.Tool, result[2].Role);
        Assert.Contains("initialAgent", result[2].AuthorName);

        Assert.Equal(ChatRole.Assistant, result[3].Role);
        Assert.Equal("", result[3].Text);
        Assert.Contains("secondAgent", result[3].AuthorName);

        Assert.Equal(ChatRole.Tool, result[4].Role);
        Assert.Contains("secondAgent", result[4].AuthorName);

        Assert.Equal(ChatRole.Assistant, result[5].Role);
        Assert.Equal("Hello from agent3", result[5].Text);
        Assert.Contains("thirdAgent", result[5].AuthorName);
    }

    private static async Task<(string UpdateText, List<ChatMessage>? Result)> RunWorkflowAsync(
        Workflow<List<ChatMessage>> workflow, List<ChatMessage> input)
    {
        StringBuilder sb = new();

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        WorkflowCompletedEvent? completed = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is AgentRunUpdateEvent executorComplete)
            {
                sb.Append(executorComplete.Data);
            }
            else if (evt is WorkflowCompletedEvent e)
            {
                completed = e;
                break;
            }
        }

        return (sb.ToString(), completed?.Data as List<ChatMessage>);
    }

    private sealed class DoubleEchoAgentWithBarrier(string name, StrongBox<TaskCompletionSource<bool>> barrier, StrongBox<int> remaining) : DoubleEchoAgent(name)
    {
        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (Interlocked.Decrement(ref remaining.Value) == 0)
            {
                barrier.Value!.SetResult(true);
            }

            await barrier.Value!.Task.ConfigureAwait(false);

            await foreach (var update in base.RunStreamingAsync(messages, thread, options, cancellationToken))
            {
                await Task.Yield();
                yield return update;
            }
        }
    }

    private sealed class MockChatClient(Func<IEnumerable<ChatMessage>, ChatOptions?, ChatResponse> responseFactory) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(responseFactory(messages, options));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (var update in (await this.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false)).ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;
        public void Dispose() { }
    }
}
