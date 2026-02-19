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
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AgentWorkflowBuilderTests
{
    [Fact]
    public void BuildSequential_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(workflowName: null!, null!));
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
        Assert.Throws<ArgumentNullException>("initialAgent", () => AgentWorkflowBuilder.CreateHandoffBuilderWith(null!));

        var agent = new DoubleEchoAgent("agent");
        var handoffs = AgentWorkflowBuilder.CreateHandoffBuilderWith(agent);
        Assert.NotNull(handoffs);

        Assert.Throws<ArgumentNullException>("from", () => handoffs.WithHandoff(null!, new DoubleEchoAgent("a2")));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoff(new DoubleEchoAgent("a2"), null!));

        Assert.Throws<ArgumentNullException>("from", () => handoffs.WithHandoffs(null!, new DoubleEchoAgent("a2")));
        Assert.Throws<ArgumentNullException>("from", () => handoffs.WithHandoffs([null!], new DoubleEchoAgent("a2")));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoffs(new DoubleEchoAgent("a2"), null!));
        Assert.Throws<ArgumentNullException>("to", () => handoffs.WithHandoffs(new DoubleEchoAgent("a2"), [null!]));

        var noDescriptionAgent = new ChatClientAgent(new MockChatClient(delegate { return new(); }));
        Assert.Throws<ArgumentException>("to", () => handoffs.WithHandoff(agent, noDescriptionAgent));
    }

    [Fact]
    public void BuildGroupChat_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("managerFactory", () => AgentWorkflowBuilder.CreateGroupChatBuilderWith(null!));

        var groupChat = AgentWorkflowBuilder.CreateGroupChatBuilderWith(_ => new RoundRobinGroupChatManager([new DoubleEchoAgent("a1")]));
        Assert.NotNull(groupChat);
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(null!));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants([null!]));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(new DoubleEchoAgent("a1"), null!));

        Assert.Throws<ArgumentNullException>("agents", () => new RoundRobinGroupChatManager(null!));
    }

    [Fact]
    public void GroupChatManager_MaximumIterationCount_Invalid_Throws()
    {
        var manager = new RoundRobinGroupChatManager([new DoubleEchoAgent("a1")]);

        const int DefaultMaxIterations = 40;
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = 0);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = -1);
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 30;
        Assert.Equal(30, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 1;
        Assert.Equal(1, manager.MaximumIterationCount);

        manager.MaximumIterationCount = int.MaxValue;
        Assert.Equal(int.MaxValue, manager.MaximumIterationCount);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task BuildSequential_AgentsRunInOrderAsync(int numAgents)
    {
        var workflow = AgentWorkflowBuilder.BuildSequential(
            from i in Enumerable.Range(1, numAgents)
            select new DoubleEchoAgent($"agent{i}"));

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(numAgents + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[numAgents + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < numAgents + 1; i++)
            {
                string id = $"agent{((i - 1) % numAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }

    private class DoubleEchoAgent(string name) : AIAgent
    {
        public override string Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            var contents = messages.SelectMany(m => m.Contents).ToList();
            string id = Guid.NewGuid().ToString("N");
            yield return new AgentResponseUpdate(ChatRole.Assistant, this.Name) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
        }
    }

    private sealed class DoubleEchoAgentSession() : AgentSession();

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
            Assert.NotEmpty(updateText);
            Assert.NotNull(result);

            // TODO: https://github.com/microsoft/agent-framework/issues/784
            // These asserts are flaky until we guarantee message delivery order.
            Assert.Single(Regex.Matches(updateText, "agent1"));
            Assert.Single(Regex.Matches(updateText, "agent2"));
            Assert.Equal(4, Regex.Matches(updateText, "abc").Count);
            Assert.Equal(2, result.Count);
        }
    }

    [Fact]
    public async Task Handoffs_NoTransfers_ResponseServedByOriginalAgentAsync()
    {
        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            ChatMessage message = Assert.Single(messages);
            Assert.Equal("abc", Assert.IsType<TextContent>(Assert.Single(message.Contents)).Text);

            return new(new ChatMessage(ChatRole.Assistant, "Hello from agent1"));
        }));

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
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
            new(new ChatMessage(ChatRole.Assistant, "Hello from agent2"))),
            name: "nextAgent",
            description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
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
    public async Task Handoffs_OneTransfer_HandoffTargetDoesNotReceiveHandoffFunctionMessagesAsync()
    {
        // Regression test for https://github.com/microsoft/agent-framework/issues/3161
        // When a handoff occurs, the target agent should receive the original user message
        // but should NOT receive the handoff function call or tool result messages from the
        // source agent, as these confuse the target LLM into ignoring the user's question.

        List<ChatMessage>? capturedNextAgentMessages = null;

        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var nextAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedNextAgentMessages = messages.ToList();
            return new(new ChatMessage(ChatRole.Assistant, "The derivative of x^2 is 2x."));
        }),
            name: "nextAgent",
            description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, nextAgent)
            .Build();

        _ = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "What is the derivative of x^2?")]);

        Assert.NotNull(capturedNextAgentMessages);

        // The target agent should see the original user message
        Assert.Contains(capturedNextAgentMessages, m => m.Role == ChatRole.User && m.Text == "What is the derivative of x^2?");

        // The target agent should NOT see the handoff function call or tool result from the source agent
        Assert.DoesNotContain(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name.StartsWith("handoff_to_", StringComparison.Ordinal)));
        Assert.DoesNotContain(capturedNextAgentMessages, m => m.Role == ChatRole.Tool && m.Contents.Any(c => c is FunctionResultContent frc && frc.Result?.ToString() == "Transferred."));
    }

    [Fact]
    public async Task Handoffs_TwoTransfers_HandoffTargetsDoNotReceiveHandoffFunctionMessagesAsync()
    {
        // Regression test for https://github.com/microsoft/agent-framework/issues/3161
        // With two hops (initial -> second -> third), each target agent should receive the
        // original user message and text responses from prior agents (as User role), but
        // NOT any handoff function call or tool result messages.

        List<ChatMessage>? capturedSecondAgentMessages = null;
        List<ChatMessage>? capturedThirdAgentMessages = null;

        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            // Return both a text message and a handoff function call
            return new(new ChatMessage(ChatRole.Assistant, [new TextContent("Routing to second agent"), new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var secondAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedSecondAgentMessages = messages.ToList();

            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            // Return both a text message and a handoff function call
            return new(new ChatMessage(ChatRole.Assistant, [new TextContent("Routing to third agent"), new FunctionCallContent("call2", transferFuncName)]));
        }), name: "secondAgent", description: "The second agent");

        var thirdAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedThirdAgentMessages = messages.ToList();
            return new(new ChatMessage(ChatRole.Assistant, "Hello from agent3"));
        }),
            name: "thirdAgent",
            description: "The third / final agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, secondAgent)
            .WithHandoff(secondAgent, thirdAgent)
            .Build();

        (string updateText, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.Contains("Hello from agent3", updateText);

        // Second agent should see the original user message and initialAgent's text as context
        Assert.NotNull(capturedSecondAgentMessages);
        Assert.Contains(capturedSecondAgentMessages, m => m.Text == "abc");
        Assert.Contains(capturedSecondAgentMessages, m => m.Text!.Contains("Routing to second agent"));
        Assert.DoesNotContain(capturedSecondAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name.StartsWith("handoff_to_", StringComparison.Ordinal)));
        Assert.DoesNotContain(capturedSecondAgentMessages, m => m.Role == ChatRole.Tool && m.Contents.Any(c => c is FunctionResultContent));

        // Third agent should see the original user message and both prior agents' text as context
        Assert.NotNull(capturedThirdAgentMessages);
        Assert.Contains(capturedThirdAgentMessages, m => m.Text == "abc");
        Assert.Contains(capturedThirdAgentMessages, m => m.Text!.Contains("Routing to second agent"));
        Assert.Contains(capturedThirdAgentMessages, m => m.Text!.Contains("Routing to third agent"));
        Assert.DoesNotContain(capturedThirdAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name.StartsWith("handoff_to_", StringComparison.Ordinal)));
        Assert.DoesNotContain(capturedThirdAgentMessages, m => m.Role == ChatRole.Tool && m.Contents.Any(c => c is FunctionResultContent));
    }

    [Fact]
    public async Task Handoffs_FilteringNone_HandoffTargetReceivesAllMessagesIncludingToolCallsAsync()
    {
        // With filtering set to None, the target agent should see everything including
        // handoff function calls and tool results.

        List<ChatMessage>? capturedNextAgentMessages = null;

        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var nextAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedNextAgentMessages = messages.ToList();
            return new(new ChatMessage(ChatRole.Assistant, "response"));
        }),
            name: "nextAgent",
            description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, nextAgent)
            .WithToolCallFilteringBehavior(HandoffToolCallFilteringBehavior.None)
            .Build();

        _ = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "hello")]);

        Assert.NotNull(capturedNextAgentMessages);
        Assert.Contains(capturedNextAgentMessages, m => m.Text == "hello");

        // With None filtering, handoff function calls and tool results should be visible
        Assert.Contains(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name.StartsWith("handoff_to_", StringComparison.Ordinal)));
        Assert.Contains(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionResultContent));
    }

    [Fact]
    public async Task Handoffs_FilteringAll_HandoffTargetDoesNotReceiveAnyToolCallsAsync()
    {
        // With filtering set to All, the target agent should see no function calls or tool
        // results at all — not even non-handoff ones from prior conversation history.

        List<ChatMessage>? capturedNextAgentMessages = null;

        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new TextContent("Routing you now"), new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var nextAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedNextAgentMessages = messages.ToList();
            return new(new ChatMessage(ChatRole.Assistant, "response"));
        }),
            name: "nextAgent",
            description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, nextAgent)
            .WithToolCallFilteringBehavior(HandoffToolCallFilteringBehavior.All)
            .Build();

        // Input includes a pre-existing non-handoff tool call in the conversation history
        List<ChatMessage> input =
        [
            new(ChatRole.User, "What's the weather? Also help me with math."),
            new(ChatRole.Assistant, [new FunctionCallContent("toolcall1", "get_weather")]) { AuthorName = "initialAgent" },
            new(ChatRole.Tool, [new FunctionResultContent("toolcall1", "sunny")]),
            new(ChatRole.Assistant, "The weather is sunny. Now let me route your math question.") { AuthorName = "initialAgent" },
        ];

        _ = await RunWorkflowAsync(workflow, input);

        Assert.NotNull(capturedNextAgentMessages);

        // With All filtering, NO function calls or tool results should be visible
        Assert.DoesNotContain(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent));
        Assert.DoesNotContain(capturedNextAgentMessages, m => m.Role == ChatRole.Tool);

        // But text content should still be visible
        Assert.Contains(capturedNextAgentMessages, m => m.Text!.Contains("What's the weather"));
        Assert.Contains(capturedNextAgentMessages, m => m.Text!.Contains("Routing you now"));
    }

    [Fact]
    public async Task Handoffs_FilteringHandoffOnly_PreservesNonHandoffToolCallsAsync()
    {
        // With HandoffOnly filtering (the default), non-handoff function calls and tool
        // results should be preserved while handoff ones are stripped.

        List<ChatMessage>? capturedNextAgentMessages = null;

        var initialAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "initialAgent");

        var nextAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            capturedNextAgentMessages = messages.ToList();
            return new(new ChatMessage(ChatRole.Assistant, "response"));
        }),
            name: "nextAgent",
            description: "The second agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, nextAgent)
            .WithToolCallFilteringBehavior(HandoffToolCallFilteringBehavior.HandoffOnly)
            .Build();

        // Input includes a pre-existing non-handoff tool call in the conversation history
        List<ChatMessage> input =
        [
            new(ChatRole.User, "What's the weather? Also help me with math."),
            new(ChatRole.Assistant, [new FunctionCallContent("toolcall1", "get_weather")]) { AuthorName = "initialAgent" },
            new(ChatRole.Tool, [new FunctionResultContent("toolcall1", "sunny")]),
            new(ChatRole.Assistant, "The weather is sunny. Now let me route your math question.") { AuthorName = "initialAgent" },
        ];

        _ = await RunWorkflowAsync(workflow, input);

        Assert.NotNull(capturedNextAgentMessages);

        // Handoff function calls and their tool results should be filtered
        Assert.DoesNotContain(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name.StartsWith("handoff_to_", StringComparison.Ordinal)));

        // Non-handoff function calls and their tool results should be preserved
        Assert.Contains(capturedNextAgentMessages, m => m.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "get_weather"));
        Assert.Contains(capturedNextAgentMessages, m => m.Role == ChatRole.Tool && m.Contents.Any(c => c is FunctionResultContent frc && frc.CallId == "toolcall1"));
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
            new(new ChatMessage(ChatRole.Assistant, "Hello from agent3"))),
            name: "thirdAgent",
            description: "The third / final agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
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

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task BuildGroupChat_AgentsRunInOrderAsync(int maxIterations)
    {
        const int NumAgents = 3;
        var workflow = AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxIterations })
            .AddParticipants(new DoubleEchoAgent("agent1"), new DoubleEchoAgent("agent2"))
            .AddParticipants(new DoubleEchoAgent("agent3"))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(maxIterations + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[maxIterations + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < maxIterations + 1; i++)
            {
                string id = $"agent{((i - 1) % NumAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }

    private static async Task<(string UpdateText, List<ChatMessage>? Result)> RunWorkflowAsync(
        Workflow workflow, List<ChatMessage> input, ExecutionEnvironment executionEnvironment = ExecutionEnvironment.InProcess_Lockstep)
    {
        StringBuilder sb = new();

        InProcessExecutionEnvironment environment = executionEnvironment.ToWorkflowExecutionEnvironment();
        await using StreamingRun run = await environment.StreamAsync(workflow, input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        WorkflowOutputEvent? output = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is AgentResponseUpdateEvent executorComplete)
            {
                sb.Append(executorComplete.Data);
            }
            else if (evt is WorkflowOutputEvent e)
            {
                output = e;
                break;
            }
            else if (evt is WorkflowErrorEvent errorEvent)
            {
                Assert.Fail($"Workflow execution failed with error: {errorEvent.Exception}");
            }
        }

        return (sb.ToString(), output?.As<List<ChatMessage>>());
    }

    private sealed class DoubleEchoAgentWithBarrier(string name, StrongBox<TaskCompletionSource<bool>> barrier, StrongBox<int> remaining) : DoubleEchoAgent(name)
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (Interlocked.Decrement(ref remaining.Value) == 0)
            {
                barrier.Value!.SetResult(true);
            }

            await barrier.Value!.Task.ConfigureAwait(false);

            await foreach (var update in base.RunCoreStreamingAsync(messages, session, options, cancellationToken))
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
