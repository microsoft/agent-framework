// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class AIAgentHostExecutorTests : AIAgentHostingExecutorTestsBase
{
    [Theory]
    [InlineData(null, null)]
    [InlineData(null, true)]
    [InlineData(null, false)]
    [InlineData(true, null)]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, null)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task Test_AgentHostExecutor_EmitsStreamingUpdatesIFFConfiguredAsync(bool? executorSetting, bool? turnSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentUpdateEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(turnSetting), testContext.BindWorkflowContext(executor.Id));

        // Assert
        // The rules are: TurnToken overrides Agent, if set. Default to false, if both unset.
        bool expectingEvents = turnSetting ?? executorSetting ?? false;

        AgentResponseUpdateEvent[] updates = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        CheckResponseUpdateEventsAgainstTestMessages(updates, expectingEvents, agent.GetDescriptiveId());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_AgentHostExecutor_EmitsResponseIFFConfiguredAsync(bool executorSetting)
    {
        // Arrange
        TestRunContext testContext = new();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { EmitAgentResponseEvents = executorSetting });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
    }

    private static ChatMessage UserMessage => new(ChatRole.User, "Hello from User!") { AuthorName = "User" };
    private static ChatMessage AssistantMessage => new(ChatRole.Assistant, "Hello from Assistant!") { AuthorName = "User" };
    private static ChatMessage TestAgentMessage => new(ChatRole.Assistant, $"Hello from {TestAgentName}!") { AuthorName = TestAgentName };

    [Theory]
    [InlineData(true, true, false, false)]
    [InlineData(true, true, false, true)]
    [InlineData(true, true, true, false)]
    [InlineData(true, true, true, true)]
    [InlineData(true, false, false, false)]
    [InlineData(true, false, false, true)]
    [InlineData(true, false, true, false)]
    [InlineData(true, false, true, true)]
    [InlineData(false, true, false, false)]
    [InlineData(false, true, false, true)]
    [InlineData(false, true, true, false)]
    [InlineData(false, true, true, true)]
    [InlineData(false, false, false, false)]
    [InlineData(false, false, false, true)]
    [InlineData(false, false, true, false)]
    [InlineData(false, false, true, true)]
    public async Task Test_AgentHostExecutor_ReassignsRolesIFFConfiguredAsync(bool executorSetting, bool includeUser, bool includeSelfMessages, bool includeOtherMessages)
    {
        // Arrange
        TestRunContext testContext = new();
        RoleCheckAgent agent = new(false, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new() { ReassignOtherAgentsAsUsers = executorSetting });
        testContext.ConfigureExecutor(executor);

        List<ChatMessage> messages = [];

        if (includeUser)
        {
            messages.Add(UserMessage);
        }

        if (includeSelfMessages)
        {
            messages.Add(TestAgentMessage);
        }

        if (includeOtherMessages)
        {
            messages.Add(AssistantMessage);
        }

        // Act
        await executor.Router.RouteMessageAsync(messages, testContext.BindWorkflowContext(executor.Id));

        Func<Task> act = async () => await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        bool shouldThrow = includeOtherMessages && !executorSetting;

        if (shouldThrow)
        {
            await act.Should().ThrowAsync<InvalidOperationException>();
        }
        else
        {
            await act.Should().NotThrowAsync();
        }
    }

    [Theory]
    [InlineData(true, TestAgentRequestType.FunctionCall)]
    [InlineData(false, TestAgentRequestType.FunctionCall)]
    //[InlineData(true, TestAgentRequestType.UserInputRequest)] TODO: Enable when we support polymorphic routing
    [InlineData(false, TestAgentRequestType.UserInputRequest)]
    public async Task Test_AgentHostExecutor_InterceptsRequestsIFFConfiguredAsync(bool intercept, TestAgentRequestType requestType)
    {
        const int UnpairedRequestCount = 2;
        const int PairedRequestCount = 3;

        // Arrange
        TestRunContext testContext = new();
        TestRequestAgent agent = new(requestType, UnpairedRequestCount, PairedRequestCount, TestAgentId, TestAgentName);
        AIAgentHostOptions agentHostOptions = requestType switch
        {
            TestAgentRequestType.FunctionCall =>
                new()
                {
                    EmitAgentResponseEvents = true,
                    InterceptUnterminatedFunctionCalls = intercept
                },
            TestAgentRequestType.UserInputRequest =>
                new()
                {
                    EmitAgentResponseEvents = true,
                    InterceptUserInputRequests = intercept
                },
            _ => throw new NotSupportedException()
        };

        AIAgentHostExecutor executor = new(agent, agentHostOptions);
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        List<object> responses;
        if (intercept)
        {
            // We expect to have a sent message containing the requests as an ExternalRequest
            switch (requestType)
            {
                case TestAgentRequestType.FunctionCall:
                    responses = ExtractAndValidateRequestContents<FunctionCallContent>();
                    break;
                case TestAgentRequestType.UserInputRequest:
                    responses = ExtractAndValidateRequestContents<ToolApprovalRequestContent>();
                    break;
                default:
                    throw new NotSupportedException();
            }

            List<object> ExtractAndValidateRequestContents<TRequest>() where TRequest : AIContent
            {
                IEnumerable<TRequest> requests = testContext.QueuedMessages.Should().ContainKey(executor.Id)
                                                            .WhoseValue
                                                            .Select(envelope => envelope.Message as TRequest)
                                                            .Where(item => item is not null)
                                                            .Select(item => item!);

                return agent.ValidateUnpairedRequests(requests).ToList();
            }
        }
        else
        {
            responses = agent.ValidateUnpairedRequests([.. testContext.ExternalRequests]).ToList<object>();
        }

        // Act 2
        foreach (object response in responses.Take(UnpairedRequestCount - 1))
        {
            await executor.Router.RouteMessageAsync(response, testContext.BindWorkflowContext(executor.Id));
        }

        // Assert 2
        // Since we are not finished, we expect the agent to not have produced a final response (="Remaining: 1")
        AgentResponseEvent lastResponseEvent = testContext.Events.OfType<AgentResponseEvent>().Should().NotBeEmpty()
                                                                                                    .And.Subject.Last();

        lastResponseEvent.Response.Text.Should().Be("Remaining: 1");

        // Act 3
        object finalResponse = responses.Last();
        await executor.Router.RouteMessageAsync(finalResponse, testContext.BindWorkflowContext(executor.Id));

        // Assert 3
        // Now that we are finished, we expect the agent to have produced a final response
        lastResponseEvent = testContext.Events.OfType<AgentResponseEvent>().Should().NotBeEmpty()
                                                                              .And.Subject.Last();

        lastResponseEvent.Response.Text.Should().Be("Done");
    }

    #region FilterForwardableMessages tests

    /// <summary>
    /// An agent that returns response messages containing a mix of content types,
    /// including non-portable server-side artifacts like TextReasoningContent and
    /// unrecognized AIContent subclasses (simulating mcp_list_tools, web_search_call, etc.).
    /// </summary>
    private sealed class MixedContentAgent(List<ChatMessage> responseMessages, string? id = null, string? name = null) : AIAgent
    {
        protected override string? IdCore => id;
        public override string? Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new MixedContentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new MixedContentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new AgentResponse(responseMessages.ToList()) { AgentId = this.Id });

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (ChatMessage msg in responseMessages)
            {
                foreach (AIContent content in msg.Contents)
                {
                    yield return new AgentResponseUpdate
                    {
                        AgentId = this.Id,
                        AuthorName = this.Name,
                        MessageId = msg.MessageId ?? Guid.NewGuid().ToString("N"),
                        ResponseId = Guid.NewGuid().ToString("N"),
                        Contents = [content],
                        Role = msg.Role,
                    };
                }
            }
        }

        private sealed class MixedContentSession : AgentSession;
    }

    /// <summary>
    /// A custom AIContent subclass that simulates an unrecognized provider-specific content type
    /// (e.g. mcp_list_tools, web_search_call, fabric_dataagent_preview_call).
    /// </summary>
    private sealed class UnrecognizedServerContent(string description) : AIContent
    {
        public string Description => description;
    }

    [Fact]
    public async Task Test_AgentHostExecutor_FiltersNonPortableContentFromForwardedMessagesAsync()
    {
        // Arrange: agent returns a mix of text, reasoning, and unrecognized content
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, [new TextContent("Useful response text")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = "original_response_item_1",
            },
            new(ChatRole.Assistant, [new TextReasoningContent("internal thinking")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = "original_reasoning_item",
            },
            new(ChatRole.Assistant, [new UnrecognizedServerContent("mcp_list_tools payload")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = "original_mcp_list_tools_item",
            },
        };

        TestRunContext testContext = new();
        MixedContentAgent agent = new(responseMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new());
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert: only the text message should be forwarded
        testContext.QueuedMessages.Should().ContainKey(executor.Id);
        List<MessageEnvelope> sentEnvelopes = testContext.QueuedMessages[executor.Id];

        // Extract forwarded ChatMessage lists (filter out TurnToken)
        List<ChatMessage> forwardedMessages = sentEnvelopes
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        forwardedMessages.Should().HaveCount(1);
        forwardedMessages[0].Role.Should().Be(ChatRole.Assistant);
        forwardedMessages[0].Contents.Should().HaveCount(1);
        forwardedMessages[0].Contents[0].Should().BeOfType<TextContent>();
        ((TextContent)forwardedMessages[0].Contents[0]).Text.Should().Be("Useful response text");
    }

    [Fact]
    public async Task Test_AgentHostExecutor_StripsRawRepresentationFromForwardedMessagesAsync()
    {
        // Arrange: agent returns a text message with RawRepresentation set
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, [new TextContent("Response")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = "provider_specific_response_item",
            },
        };

        TestRunContext testContext = new();
        MixedContentAgent agent = new(responseMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new());
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert: forwarded message should NOT have RawRepresentation
        List<ChatMessage> forwardedMessages = testContext.QueuedMessages[executor.Id]
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        forwardedMessages.Should().HaveCount(1);
        forwardedMessages[0].RawRepresentation.Should().BeNull();
        forwardedMessages[0].AuthorName.Should().Be(TestAgentName);
    }

    [Fact]
    public async Task Test_AgentHostExecutor_PreservesForwardableContentInMixedMessagesAsync()
    {
        // Arrange: a single message with both text and reasoning content
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant,
            [
                new TextContent("Visible text"),
                new TextReasoningContent("Hidden reasoning"),
                new FunctionCallContent("call_1", "my_function", new Dictionary<string, object?> { ["arg"] = "val" }),
            ])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = "original_mixed_item",
            },
        };

        TestRunContext testContext = new();
        MixedContentAgent agent = new(responseMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new());
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert: message should be forwarded with only the text and function call content
        List<ChatMessage> forwardedMessages = testContext.QueuedMessages[executor.Id]
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        forwardedMessages.Should().HaveCount(1);
        ChatMessage forwarded = forwardedMessages[0];
        forwarded.Contents.Should().HaveCount(2);
        forwarded.Contents[0].Should().BeOfType<TextContent>();
        forwarded.Contents[1].Should().BeOfType<FunctionCallContent>();
        forwarded.RawRepresentation.Should().BeNull();
    }

    [Fact]
    public async Task Test_AgentHostExecutor_DropsMessageWithOnlyNonPortableContentAsync()
    {
        // Arrange: agent returns only non-portable content
        var responseMessages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, [new TextReasoningContent("reasoning only")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
            },
            new(ChatRole.Assistant, [new UnrecognizedServerContent("web_search_call")])
            {
                AuthorName = TestAgentName,
                MessageId = Guid.NewGuid().ToString("N"),
            },
        };

        TestRunContext testContext = new();
        MixedContentAgent agent = new(responseMessages, TestAgentId, TestAgentName);
        AIAgentHostExecutor executor = new(agent, new());
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert: no ChatMessage lists should be forwarded (only TurnToken)
        List<ChatMessage> forwardedMessages = testContext.QueuedMessages[executor.Id]
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        forwardedMessages.Should().BeEmpty();
    }

    #endregion
}
