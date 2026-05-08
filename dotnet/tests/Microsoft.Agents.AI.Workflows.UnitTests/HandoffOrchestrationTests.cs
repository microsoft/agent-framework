// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffOrchestrationTests
{
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

        var emptyDescriptionAgent = new MockChatClient(delegate { return new(); }).AsAIAgent(description: "");
        Assert.Throws<ArgumentException>("to", () => handoffs.WithHandoff(agent, emptyDescriptionAgent));

        var emptyNameAgent = new MockChatClient(delegate { return new(); }).AsAIAgent(name: "");
        Assert.Throws<ArgumentException>("to", () => handoffs.WithHandoff(agent, emptyNameAgent));
    }

    private sealed class NullLogger : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull
        {
            return null;
        }

        public bool IsEnabled(LogLevel logLevel)
        {
            return false;
        }

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
        }
    }

    [Fact]
    public void BuildHandoffs_DelegatingAIAgent_DoesNotThrow()
    {
        DoubleEchoAgent agent = new("agent");
        HandoffWorkflowBuilder handoffs = AgentWorkflowBuilder.CreateHandoffBuilderWith(agent);
        Assert.NotNull(handoffs);

        ChatClientAgent instructionsOnlyAgent = new MockChatClient(delegate { return new(); }).AsAIAgent(instructions: "instructions");
        LoggingAgent delegatingAgent = new(instructionsOnlyAgent, new NullLogger());

        handoffs.WithHandoff(agent, delegatingAgent);

        // get the _targets field from the HandoffWorkflowBuilder (need to use the base type)
        FieldInfo field = typeof(HandoffWorkflowBuilder).BaseType!.GetField("_targets", BindingFlags.Instance | BindingFlags.NonPublic)!;
        Dictionary<AIAgent, HashSet<HandoffTarget>>? targets = field.GetValue(handoffs) as Dictionary<AIAgent, HashSet<HandoffTarget>>;

        targets.Should().NotBeNull();

        HandoffTarget target = targets[agent].Single();
        target.Reason.Should().Be("instructions");
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

        (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

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

        (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

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

        (string updateText, _, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

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

        (string updateText, List<ChatMessage>? result, _, _) = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

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

    [Fact]
    public async Task Handoffs_TwoTransfers_SecondAgentUserApproval_ResponseServedByThirdAgentAsync()
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

        bool secondAgentInvoked = false;

        const string SomeOtherFunctionCallId = "call2first";

        AIFunction someOtherFunction = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(SomeOtherFunction));

        var secondAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            if (!secondAgentInvoked)
            {
                secondAgentInvoked = true;
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(SomeOtherFunctionCallId, someOtherFunction.Name)]));
            }

            // Second agent should receive the conversation so far (including previous assistant + tool messages eventually).
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call2", transferFuncName)]));
        }), name: "secondAgent", description: "The second agent", tools: [someOtherFunction]);

        var thirdAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
            new(new ChatMessage(ChatRole.Assistant, "Hello from agent3"))),
            name: "thirdAgent",
            description: "The third / final agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, secondAgent)
            .WithHandoff(secondAgent, thirdAgent)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        (string updateText, List<ChatMessage>? result, CheckpointInfo? lastCheckpoint, List<RequestInfoEvent> requests) =
            await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "abc")], Environment, checkpointManager);

        Assert.Null(result);
        Assert.NotNull(requests);

        requests.Should().HaveCount(1);
        ExternalRequest request = requests[0].Request;

        ToolApprovalRequestContent approvalRequest =
            request.Data.As<ToolApprovalRequestContent>().Should().NotBeNull()
                                                              .And.Subject.As<ToolApprovalRequestContent>();

        approvalRequest.ToolCall.CallId.Should().Be(SomeOtherFunctionCallId);

        ExternalResponse response = request.CreateResponse(approvalRequest.CreateResponse(false, "Denied"));

        (updateText, result, _, requests) =
            await RunWorkflowCheckpointedAsync(workflow, response, Environment, checkpointManager, lastCheckpoint);

        Assert.Equal("Hello from agent3", updateText);
        Assert.NotNull(result);

        // User + (assistant empty + tool) for each of first two agents + final assistant with text.
        Assert.Equal(10, result.Count);

        Assert.Equal(ChatRole.User, result[0].Role);
        Assert.Equal("abc", result[0].Text);

        Assert.Equal(ChatRole.Assistant, result[1].Role);
        Assert.Equal("", result[1].Text);
        Assert.Contains("initialAgent", result[1].AuthorName);

        Assert.Equal(ChatRole.Tool, result[2].Role);
        Assert.Contains("initialAgent", result[2].AuthorName);

        // Non-handoff tool invocation (and user denial)
        Assert.Equal(ChatRole.Assistant, result[3].Role);
        Assert.Equal("", result[3].Text);
        Assert.Contains("secondAgent", result[3].AuthorName);

        Assert.Equal(ChatRole.User, result[4].Role);
        Assert.Equal("", result[4].Text);

        // Rejected tool call
        Assert.Equal(ChatRole.Assistant, result[5].Role);
        Assert.Equal("", result[5].Text);
        Assert.Contains("secondAgent", result[5].AuthorName);

        Assert.Equal(ChatRole.Tool, result[6].Role);
        Assert.Contains("secondAgent", result[6].AuthorName);

        // Handoff invocation
        Assert.Equal(ChatRole.Assistant, result[7].Role);
        Assert.Equal("", result[7].Text);
        Assert.Contains("secondAgent", result[7].AuthorName);

        Assert.Equal(ChatRole.Tool, result[8].Role);
        Assert.Contains("secondAgent", result[8].AuthorName);

        Assert.Equal(ChatRole.Assistant, result[9].Role);
        Assert.Equal("Hello from agent3", result[9].Text);
        Assert.Contains("thirdAgent", result[9].AuthorName);

        static bool SomeOtherFunction() => true;
    }

    [Fact]
    public async Task Handoffs_TwoTransfers_SecondAgentToolCall_ResponseServedByThirdAgentAsync()
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

        bool secondAgentInvoked = false;

        const string SomeOtherFunctionName = "SomeOtherFunction";
        const string SomeOtherFunctionCallId = "call2first";

        JsonElement otherFunctionSchema = AIFunctionFactory.Create(() => true).JsonSchema;
        AIFunctionDeclaration someOtherFunction = AIFunctionFactory.CreateDeclaration(SomeOtherFunctionName, "Another function", otherFunctionSchema);

        var secondAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            if (!secondAgentInvoked)
            {
                secondAgentInvoked = true;
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(SomeOtherFunctionCallId, SomeOtherFunctionName)]));
            }

            // Second agent should receive the conversation so far (including previous assistant + tool messages eventually).
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);

            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call2", transferFuncName)]));
        }), name: "secondAgent", description: "The second agent", tools: [someOtherFunction]);

        var thirdAgent = new ChatClientAgent(new MockChatClient((messages, options) =>
            new(new ChatMessage(ChatRole.Assistant, "Hello from agent3"))),
            name: "thirdAgent",
            description: "The third / final agent");

        var workflow =
            AgentWorkflowBuilder.CreateHandoffBuilderWith(initialAgent)
            .WithHandoff(initialAgent, secondAgent)
            .WithHandoff(secondAgent, thirdAgent)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        (string updateText, List<ChatMessage>? result, CheckpointInfo? lastCheckpoint, List<RequestInfoEvent> requests) =
            await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "abc")], Environment, checkpointManager);

        Assert.Null(result);
        Assert.NotNull(requests);

        requests.Should().HaveCount(1);
        ExternalRequest request = requests[0].Request;

        FunctionCallContent functionCall = request.Data.As<FunctionCallContent>().Should().NotBeNull()
                                                                                 .And.Subject.As<FunctionCallContent>();

        functionCall.CallId.Should().Be(SomeOtherFunctionCallId);
        functionCall.Name.Should().Be(SomeOtherFunctionName);

        ExternalResponse response = request.CreateResponse(new FunctionResultContent(functionCall.CallId, true));

        (updateText, result, _, requests) =
            await RunWorkflowCheckpointedAsync(workflow, response, Environment, checkpointManager, lastCheckpoint);

        Assert.Equal("Hello from agent3", updateText);
        Assert.NotNull(result);

        // User + (assistant empty + tool) for each of first two agents + final assistant with text.
        Assert.Equal(8, result.Count);

        Assert.Equal(ChatRole.User, result[0].Role);
        Assert.Equal("abc", result[0].Text);

        Assert.Equal(ChatRole.Assistant, result[1].Role);
        Assert.Equal("", result[1].Text);
        Assert.Contains("initialAgent", result[1].AuthorName);

        Assert.Equal(ChatRole.Tool, result[2].Role);
        Assert.Contains("initialAgent", result[2].AuthorName);

        // Non-handoff tool invocation
        Assert.Equal(ChatRole.Assistant, result[3].Role);
        Assert.Equal("", result[3].Text);
        Assert.Contains("secondAgent", result[3].AuthorName);

        Assert.Equal(ChatRole.Tool, result[4].Role);
        Assert.Contains("secondAgent", result[4].AuthorName);

        // Handoff invocation
        Assert.Equal(ChatRole.Assistant, result[5].Role);
        Assert.Equal("", result[5].Text);
        Assert.Contains("secondAgent", result[5].AuthorName);

        Assert.Equal(ChatRole.Tool, result[6].Role);
        Assert.Contains("secondAgent", result[6].AuthorName);

        Assert.Equal(ChatRole.Assistant, result[7].Role);
        Assert.Equal("Hello from agent3", result[7].Text);
        Assert.Contains("thirdAgent", result[7].AuthorName);
    }

    [Fact]
    public async Task Handoffs_ReturnToPrevious_DisabledByDefault_SecondTurnRoutesViaCoordinatorAsync()
    {
        int coordinatorCallCount = 0;

        var coordinator = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            coordinatorCallCount++;
            if (coordinatorCallCount == 1)
            {
                string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
                Assert.NotNull(transferFuncName);
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
            }
            return new(new ChatMessage(ChatRole.Assistant, "coordinator responded on turn 2"));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(new MockChatClient((messages, options) =>
            new(new ChatMessage(ChatRole.Assistant, "specialist responded"))),
            name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        // Turn 1: coordinator hands off to specialist
        WorkflowRunResult result = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "book an appointment")], Environment, checkpointManager);
        Assert.Equal(1, coordinatorCallCount);

        // Turn 2: without ReturnToPrevious, coordinator should be invoked again
        _ = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "my id is 12345")], Environment, checkpointManager, result.LastCheckpoint);
        Assert.Equal(2, coordinatorCallCount);
    }

    [Fact]
    public async Task Handoffs_ReturnToPrevious_Enabled_SecondTurnRoutesDirectlyToSpecialistAsync()
    {
        int coordinatorCallCount = 0;
        int specialistCallCount = 0;

        var coordinator = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            coordinatorCallCount++;
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);
            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            specialistCallCount++;
            return new(new ChatMessage(ChatRole.Assistant, "specialist responded"));
        }), name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .EnableReturnToPrevious()
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        // Turn 1: coordinator hands off to specialist
        WorkflowRunResult result = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "book an appointment")], Environment, checkpointManager);
        Assert.Equal(1, coordinatorCallCount);
        Assert.Equal(1, specialistCallCount);

        // Turn 2: with ReturnToPrevious, specialist should be invoked directly, coordinator should NOT be called again
        _ = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "my id is 12345")], Environment, checkpointManager, result.LastCheckpoint);
        Assert.Equal(1, coordinatorCallCount); // coordinator NOT called again
        Assert.Equal(2, specialistCallCount);  // specialist called again
    }

    [Fact]
    public async Task Handoffs_ReturnToPrevious_Enabled_BeforeAnyHandoff_RoutesViaInitialAgentAsync()
    {
        int coordinatorCallCount = 0;

        var coordinator = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            coordinatorCallCount++;
            return new(new ChatMessage(ChatRole.Assistant, "coordinator responded"));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            Assert.Fail("Specialist should not be invoked.");
            return new();
        }), name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .EnableReturnToPrevious()
            .Build();

        // First turn with no prior handoff: should route to initial (coordinator) agent
        _ = await RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "hello")]);
        Assert.Equal(1, coordinatorCallCount);
    }

    [Fact]
    public async Task Handoffs_ReturnToPrevious_Enabled_AfterHandoffBackToCoordinator_NextTurnRoutesViaCoordinatorAsync()
    {
        int coordinatorCallCount = 0;
        int specialistCallCount = 0;

        var coordinator = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            coordinatorCallCount++;
            if (coordinatorCallCount == 1)
            {
                // First call: hand off to specialist
                string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
                Assert.NotNull(transferFuncName);
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call1", transferFuncName)]));
            }
            // Subsequent calls: respond without handoff
            return new(new ChatMessage(ChatRole.Assistant, "coordinator responded"));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(new MockChatClient((messages, options) =>
        {
            specialistCallCount++;
            // Specialist hands back to coordinator
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);
            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call2", transferFuncName)]));
        }), name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .WithHandoff(specialist, coordinator)
            .EnableReturnToPrevious()
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        // Turn 1: coordinator → specialist → coordinator (specialist hands back)
        WorkflowRunResult result = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "book an appointment")], Environment, checkpointManager);
        Assert.Equal(2, coordinatorCallCount); // called twice: initial handoff + receiving handback
        Assert.Equal(1, specialistCallCount);  // specialist called once, then handed back

        // Turn 2: after handoff back to coordinator, should route to coordinator (not specialist)
        _ = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "never mind")], Environment, checkpointManager, result.LastCheckpoint);
        Assert.Equal(3, coordinatorCallCount); // coordinator called again on turn 2
        Assert.Equal(1, specialistCallCount);  // specialist NOT called
    }

    private static MockChatClient CreateFunctionCallResultValidatingClient(Func<IEnumerable<ChatMessage>, ChatOptions?, ChatResponse> innerResponseFactory)
    {
        return new MockChatClient(InvokeResponseFactory);

        ChatResponse InvokeResponseFactory(IEnumerable<ChatMessage> chatMessages, ChatOptions? options)
        {
            // We do not need to keep the callResolver around because ChatClientAgent owns making sure that the function call is properly
            // resent to the underlying agent.
            StreamingToolCallResultPairMatcher callResolver = new();
            List<ChatMessage> incomingMessages = chatMessages.ToList();
            foreach (ChatMessage message in incomingMessages)
            {
                foreach (AIContent content in message.Contents)
                {
                    switch (content)
                    {
                        case FunctionCallContent functionCallContent:
                        {
                            callResolver.CollectFunctionCall(functionCallContent);
                            break;
                        }

                        case FunctionResultContent functionResultContent:
                        {
                            if (!callResolver.TryResolveFunctionCall(functionResultContent, out _))
                            {
                                throw new InvalidOperationException($"Received unexpected function result: {functionResultContent.CallId}");
                            }
                            break;
                        }

                        case McpServerToolCallContent mcpServerToolCallContent:
                        {
                            callResolver.CollectMcpServerToolCall(mcpServerToolCallContent);
                            break;
                        }

                        case McpServerToolResultContent mcpServerToolResultContent:
                        {
                            if (!callResolver.TryResolveMcpServerToolCall(mcpServerToolResultContent, out _))
                            {
                                throw new InvalidOperationException($"Received unexpected tool result: {mcpServerToolResultContent.CallId}");
                            }
                            break;
                        }
                    }
                }
            }

            // If there are still unmatched calls, we have an error
            callResolver.UnmatchedCalls.Should().BeEmpty();

            // Now we can invoke the inner response factory to generate the response
            ChatResponse response = innerResponseFactory(incomingMessages, options);

            foreach (ChatMessage message in response.Messages)
            {
                foreach (AIContent content in message.Contents)
                {
                    switch (content)
                    {
                        case FunctionCallContent functionCallContent:
                            callResolver.CollectFunctionCall(functionCallContent);
                            break;
                        case McpServerToolCallContent mcpServerToolCallContent:
                            callResolver.CollectMcpServerToolCall(mcpServerToolCallContent);
                            break;
                        case FunctionResultContent functionResultContent:
                        {
                            if (!callResolver.TryResolveFunctionCall(functionResultContent, out string? name))
                            {
                                throw new InvalidOperationException($"Produced unexpected function result: {functionResultContent.CallId}");
                            }
                            break;
                        }
                        case McpServerToolResultContent mcpServerToolResultContent:
                        {
                            if (!callResolver.TryResolveMcpServerToolCall(mcpServerToolResultContent, out string? name))
                            {
                                throw new InvalidOperationException($"Produced unexpected tool result: {mcpServerToolResultContent.CallId}");
                            }
                            break;
                        }
                    }
                }
            }

            return response;
        }
    }

    [Fact]
    public async Task Handoffs_ReentrantHandoff_FunctionResultSentToAgentOnSubsequentInvocationAsync()
    {
        // Regression test: When an agent requests a handoff, the synthesized FunctionResult for the handoff
        // must be sent back to the agent on subsequent invocations. If this doesn't happen, the agent's
        // conversation state will be broken because the LLM will receive a FunctionCall without a
        // corresponding FunctionResult.

        List<List<ChatMessage>>? specialistInvocations = [];
        int coordinatorCallCount = 0;
        int specialistCallCount = 0;

        var coordinator = new ChatClientAgent(CreateFunctionCallResultValidatingClient((messages, options) =>
        {
            coordinatorCallCount++;
            // Always hand off to specialist
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);
            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent($"coordinator_handoff_call_{coordinatorCallCount}", transferFuncName)]));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(CreateFunctionCallResultValidatingClient((messages, options) =>
        {
            specialistCallCount++;
            specialistInvocations.Add(messages.ToList());

            if (specialistCallCount == 1)
            {
                // First call: hand back to coordinator
                string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
                Assert.NotNull(transferFuncName);
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("specialist_handoff_call", transferFuncName)]));
            }

            // Subsequent calls: respond normally
            return new(new ChatMessage(ChatRole.Assistant, "specialist final response"));
        }), name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .WithHandoff(specialist, coordinator)
            .EnableReturnToPrevious()
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        // Turn 1: coordinator -> specialist -> coordinator -> specialist (specialist responds on 2nd call)
        // Flow: coordinator(1) hands off -> specialist(1) hands off -> coordinator(2) hands off -> specialist(2) responds
        WorkflowRunResult result = await RunWorkflowCheckpointedAsync(workflow, [new ChatMessage(ChatRole.User, "start")], Environment, checkpointManager);
        Assert.Equal(2, coordinatorCallCount); // initial + receiving handback from specialist
        Assert.Equal(2, specialistCallCount); // specialist invoked twice (once handed off, once responded)

        Assert.Equal(2, specialistInvocations.Count);
    }

    [Fact]
    public async Task Handoffs_MultiTurnWithHandoffAndReturn_AllFunctionCallsHaveMatchingResultsAsync()
    {
        // This test verifies that across multiple turns with handoffs going back and forth,
        // the FunctionCall/FunctionResult pairing rule is always maintained for any agent
        // that is re-invoked after previously requesting a handoff.

        List<List<ChatMessage>> coordinatorInvocations = [];
        List<List<ChatMessage>> specialistInvocations = [];

        var coordinator = new ChatClientAgent(CreateFunctionCallResultValidatingClient((messages, options) =>
        {
            coordinatorInvocations.Add(messages.ToList());
            int callCount = coordinatorInvocations.Count;

            // Coordinator always hands off to specialist
            string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
            Assert.NotNull(transferFuncName);
            return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent($"coord_call_{callCount}", transferFuncName)]));
        }), name: "coordinator");

        var specialist = new ChatClientAgent(CreateFunctionCallResultValidatingClient((messages, options) =>
        {
            specialistInvocations.Add(messages.ToList());
            int callCount = specialistInvocations.Count;

            if (callCount % 2 == 1)
            {
                // Odd invocations: hand back to coordinator
                string? transferFuncName = options?.Tools?.FirstOrDefault(t => t.Name.StartsWith("handoff_to_", StringComparison.Ordinal))?.Name;
                Assert.NotNull(transferFuncName);
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent($"spec_call_{callCount}", transferFuncName)]));
            }

            // Even invocations: respond normally
            return new(new ChatMessage(ChatRole.Assistant, $"specialist response {callCount}"));
        }), name: "specialist", description: "The specialist agent");

        var workflow = AgentWorkflowBuilder.CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .WithHandoff(specialist, coordinator)
            .EnableReturnToPrevious()
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        const ExecutionEnvironment Environment = ExecutionEnvironment.InProcess_Lockstep;

        // Turn 1: coordinator -> specialist -> coordinator -> specialist (ends with response)
        WorkflowRunResult result = await RunWorkflowCheckpointedAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "turn 1")],
            Environment,
            checkpointManager);

        // Verify FunctionCall/FunctionResult pairing for all invocations
        VerifyFunctionCallResultPairing(coordinatorInvocations, "coordinator");
        VerifyFunctionCallResultPairing(specialistInvocations, "specialist");

        // Turn 2: conversation continues
        _ = await RunWorkflowCheckpointedAsync(
            workflow,
            [new ChatMessage(ChatRole.User, "turn 2")],
            Environment,
            checkpointManager,
            result.LastCheckpoint);

        // Verify pairing again after second turn
        VerifyFunctionCallResultPairing(coordinatorInvocations, "coordinator");
        VerifyFunctionCallResultPairing(specialistInvocations, "specialist");
    }

    /// <summary>
    /// Verifies that for each invocation of an agent, all FunctionCallContent items
    /// that appear in the message history have corresponding FunctionResultContent items.
    /// </summary>
    private static void VerifyFunctionCallResultPairing(List<List<ChatMessage>> invocations, string agentName)
    {
        for (int i = 0; i < invocations.Count; i++)
        {
            List<ChatMessage> messages = invocations[i];

            // Get all FunctionCallContent and FunctionResultContent items from the messages
            var functionCalls = messages
                .SelectMany(m => m.Contents.OfType<FunctionCallContent>())
                .ToList();

            var functionResults = messages
                .SelectMany(m => m.Contents.OfType<FunctionResultContent>())
                .ToList();

            // Create lookup of call IDs that have results
            var resultCallIds = new HashSet<string>(functionResults.Select(r => r.CallId));

            // Verify each function call has a matching result
            foreach (var call in functionCalls)
            {
                Assert.True(resultCallIds.Contains(call.CallId),
                        $"Agent '{agentName}' invocation {i + 1}: FunctionCallContent with CallId '{call.CallId}' (Name: '{call.Name}') " +
                        "has no matching FunctionResultContent. This violates the LLM's requirement that all FunctionCalls have results.");
            }
        }
    }

    #region Helper Types and Methods

    private sealed record WorkflowRunResult(string UpdateText, List<ChatMessage>? Result, CheckpointInfo? LastCheckpoint, List<RequestInfoEvent> PendingRequests);

    private static Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, List<ChatMessage> input, ExecutionEnvironment executionEnvironment, CheckpointManager checkpointManager, CheckpointInfo? fromCheckpoint = null)
    {
        InProcessExecutionEnvironment environment = executionEnvironment.ToWorkflowExecutionEnvironment()
                                                                        .WithCheckpointing(checkpointManager);

        return RunWorkflowCheckpointedAsync(workflow, input, environment, fromCheckpoint);
    }

    private static Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, ExternalResponse response, ExecutionEnvironment executionEnvironment, CheckpointManager checkpointManager, CheckpointInfo? fromCheckpoint = null)
    {
        InProcessExecutionEnvironment environment = executionEnvironment.ToWorkflowExecutionEnvironment()
                                                                        .WithCheckpointing(checkpointManager);

        return RunWorkflowCheckpointedAsync(workflow, response, environment, fromCheckpoint);
    }

    private static async Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, List<ChatMessage> input, InProcessExecutionEnvironment environment, CheckpointInfo? fromCheckpoint = null)
    {
        await using StreamingRun run =
            fromCheckpoint != null ? await environment.ResumeStreamingAsync(workflow, fromCheckpoint)
                                   : await environment.OpenStreamingAsync(workflow);

        await run.TrySendMessageAsync(input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        return await ProcessWorkflowRunAsync(run);
    }

    private static async Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, ExternalResponse response, InProcessExecutionEnvironment environment, CheckpointInfo? fromCheckpoint = null)
    {
        await using StreamingRun run =
            fromCheckpoint != null ? await environment.ResumeStreamingAsync(workflow, fromCheckpoint)
                                   : await environment.OpenStreamingAsync(workflow);

        await run.SendResponseAsync(response);

        return await ProcessWorkflowRunAsync(run);
    }

    private static async Task<WorkflowRunResult> ProcessWorkflowRunAsync(StreamingRun run)
    {
        StringBuilder sb = new();
        WorkflowOutputEvent? output = null;
        CheckpointInfo? lastCheckpoint = null;

        List<RequestInfoEvent> pendingRequests = [];

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            switch (evt)
            {
                case AgentResponseUpdateEvent responseUpdate:
                    sb.Append(responseUpdate.Data);
                    break;

                case RequestInfoEvent requestInfo:
                    pendingRequests.Add(requestInfo);
                    break;

                case WorkflowOutputEvent e:
                    output = e;
                    break;

                case WorkflowErrorEvent errorEvent:
                    Assert.Fail($"Workflow execution failed with error: {errorEvent.Exception}");
                    break;

                case SuperStepCompletedEvent stepCompleted:
                    lastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
                    break;
            }
        }

        return new(sb.ToString(), output?.As<List<ChatMessage>>(), lastCheckpoint, pendingRequests);
    }

    private static Task<WorkflowRunResult> RunWorkflowAsync(
        Workflow workflow, List<ChatMessage> input, ExecutionEnvironment executionEnvironment = ExecutionEnvironment.InProcess_Lockstep)
        => RunWorkflowCheckpointedAsync(workflow, input, executionEnvironment.ToWorkflowExecutionEnvironment());

    private sealed class DoubleEchoAgent(string name) : AIAgent
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

    #endregion
}
