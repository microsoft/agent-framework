// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
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

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    public async Task Test_AgentHostExecutor_AssignsStableMessageIdToContentfulStreamingUpdatesAsync(string? missingMessageId)
    {
        // Arrange
        TestRunContext testContext = new();
        AIAgentHostExecutor executor =
            new(
                new MissingMessageIdAgent(missingMessageId),
                new()
                {
                    EmitAgentUpdateEvents = true,
                    EmitAgentResponseEvents = true,
                });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseUpdateEvent[] updateEvents = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        Assert.Equal(3, updateEvents.Length);
        Assert.Equal(string.Empty, updateEvents[0].Update.MessageId);

        string? messageId = updateEvents[1].Update.MessageId;
        Assert.False(string.IsNullOrEmpty(messageId));
        Assert.All(updateEvents.Skip(1), updateEvent => Assert.True(updateEvent.Update.MessageId == messageId));

        AgentResponseEvent responseEvent = Assert.Single(testContext.Events.OfType<AgentResponseEvent>());
        ChatMessage responseMessage = Assert.Single(responseEvent.Response.Messages);
        Assert.Equal(messageId, responseMessage.MessageId);
        Assert.Equal("hello world", responseMessage.Text);
    }

    private static ChatMessage UserMessage => new(ChatRole.User, "Hello from User!") { AuthorName = "User" };
    private static ChatMessage AssistantMessage => new(ChatRole.Assistant, "Hello from Assistant!") { AuthorName = "User" };
    private static ChatMessage TestAgentMessage => new(ChatRole.Assistant, $"Hello from {TestAgentName}!") { AuthorName = TestAgentName };

    private sealed class MissingMessageIdAgent(string? messageId) : TestReplayAgent
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return new AgentResponseUpdate(
                new ChatResponseUpdate
                {
                    MessageId = "",
                    ResponseId = "response-id",
                });
            yield return new AgentResponseUpdate(
                new ChatResponseUpdate(ChatRole.Assistant, "hello ")
                {
                    MessageId = messageId,
                    ResponseId = "response-id",
                });
            yield return new AgentResponseUpdate(ChatRole.Assistant, "world")
            {
                MessageId = messageId,
                ResponseId = "response-id",
                Role = null,
                RawRepresentation = new object(),
            };
            await Task.CompletedTask;
        }
    }

    [Fact]
    public async Task Test_AgentHostExecutor_ForwardsAgentResponseMessageAsync()
    {
        // Arrange
        ChatMessage userMessage = new(ChatRole.User, "Summarize this.") { AuthorName = "User" };
        ChatMessage responseMessage = new(ChatRole.Assistant, [new TextContent("Partial answer")])
        {
            AuthorName = TestAgentName,
            MessageId = "message-id",
            RawRepresentation = "provider-message",
        };
        ChatMessage reasoningMessage = new(ChatRole.Assistant, [new TextReasoningContent("internal reasoning")])
        {
            AuthorName = TestAgentName,
            MessageId = "reasoning-id",
            RawRepresentation = "provider-reasoning",
        };
        AgentResponse agentResponse = new([responseMessage, reasoningMessage])
        {
            AgentId = TestAgentId,
            ResponseId = "response-id",
            FinishReason = ChatFinishReason.Length,
            Usage = new UsageDetails { InputTokenCount = 10, OutputTokenCount = 2, TotalTokenCount = 12 },
            AdditionalProperties = new() { ["detail"] = "metadata" },
        };
        AIAgentHostExecutor executor = new(new FixedResponseAgent(agentResponse, TestAgentId, TestAgentName), new() { ForwardAgentResponse = true });
        TestRunContext testContext = new();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.Router.RouteMessageAsync(userMessage, testContext.BindWorkflowContext(executor.Id));
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.Contains(typeof(AIAgentHostResponse), executor.Protocol.Describe().Sends);

        IEnumerable<object> sentMessages = testContext.QueuedMessages[executor.Id].Select(envelope => envelope.Message);
        AIAgentHostResponse hostResponse = Assert.Single(sentMessages.OfType<AIAgentHostResponse>());

        Assert.Equal(executor.Id, hostResponse.ExecutorId);
        Assert.Same(agentResponse, hostResponse.AgentResponse);
        Assert.Equal(ChatFinishReason.Length, hostResponse.AgentResponse.FinishReason);
        Assert.Equal("response-id", hostResponse.AgentResponse.ResponseId);
        Assert.Equal(12, hostResponse.AgentResponse.Usage?.TotalTokenCount);
        Assert.Equal("metadata", hostResponse.AgentResponse.AdditionalProperties?["detail"]);

        ChatMessage forwardableMessage = Assert.Single(hostResponse.ForwardableMessages);
        Assert.Equal("Partial answer", forwardableMessage.Text);
        Assert.Null(forwardableMessage.RawRepresentation);

        Assert.Equal(2, hostResponse.FullConversation.Count);
        Assert.Equal("Summarize this.", hostResponse.FullConversation[0].Text);
        Assert.Equal("Partial answer", hostResponse.FullConversation[1].Text);
    }

    [Fact]
    public async Task Test_AgentHostExecutor_DoesNotForwardAgentResponseMessageByDefaultAsync()
    {
        // Arrange
        AgentResponse agentResponse = new(new ChatMessage(ChatRole.Assistant, "Hello"));
        AIAgentHostExecutor executor = new(new FixedResponseAgent(agentResponse, TestAgentId, TestAgentName), new());
        TestRunContext testContext = new();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.Contains(executor.Id, testContext.QueuedMessages);
        Assert.DoesNotContain(testContext.QueuedMessages[executor.Id], envelope => envelope.Message is AIAgentHostResponse);
    }

    private sealed class FixedResponseAgent(AgentResponse response, string? id = null, string? name = null) : AIAgent
    {
        protected override string? IdCore => id;
        public override string? Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new FixedResponseSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new FixedResponseSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(response);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (AgentResponseUpdate update in response.ToAgentResponseUpdates())
            {
                yield return update;
            }

            await Task.CompletedTask;
        }

        private sealed class FixedResponseSession : AgentSession;
    }

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

        async Task actAsync() => await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert
        bool shouldThrow = includeOtherMessages && !executorSetting;

        if (shouldThrow)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        }
        else
        {
            Assert.Null(await Record.ExceptionAsync(actAsync));
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
                IEnumerable<TRequest> requests = Assert.Contains(executor.Id, testContext.QueuedMessages)
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
        List<AgentResponseEvent> agentResponseEvents = testContext.Events.OfType<AgentResponseEvent>().ToList();
        Assert.NotEmpty(agentResponseEvents);
        AgentResponseEvent lastResponseEvent = agentResponseEvents.Last();

        Assert.Equal("Remaining: 1", lastResponseEvent.Response.Text);

        // Act 3
        object finalResponse = responses.Last();
        await executor.Router.RouteMessageAsync(finalResponse, testContext.BindWorkflowContext(executor.Id));

        // Assert 3
        // Now that we are finished, we expect the agent to have produced a final response
        agentResponseEvents = testContext.Events.OfType<AgentResponseEvent>().ToList();
        Assert.NotEmpty(agentResponseEvents);
        lastResponseEvent = agentResponseEvents.Last();

        Assert.Equal("Done", lastResponseEvent.Response.Text);
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
        Assert.Contains(executor.Id, testContext.QueuedMessages);
        List<MessageEnvelope> sentEnvelopes = testContext.QueuedMessages[executor.Id];

        // Extract forwarded ChatMessage lists (filter out TurnToken)
        List<ChatMessage> forwardedMessages = sentEnvelopes
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        Assert.Single(forwardedMessages);
        Assert.Equal(ChatRole.Assistant, forwardedMessages[0].Role);
        TextContent content = Assert.IsType<TextContent>(Assert.Single(forwardedMessages[0].Contents));
        Assert.Equal("Useful response text", content.Text);
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

        Assert.Single(forwardedMessages);
        Assert.Null(forwardedMessages[0].RawRepresentation);
        Assert.Equal(TestAgentName, forwardedMessages[0].AuthorName);
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

        Assert.Single(forwardedMessages);
        ChatMessage forwarded = forwardedMessages[0];
        Assert.Equal(2, forwarded.Contents.Count);
        Assert.IsType<TextContent>(forwarded.Contents[0]);
        Assert.IsType<FunctionCallContent>(forwarded.Contents[1]);
        Assert.Null(forwarded.RawRepresentation);
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
        AIAgentHostExecutor executor = new(agent, new() { ForwardIncomingMessages = false });
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.TakeTurnAsync(new(), testContext.BindWorkflowContext(executor.Id));

        // Assert: no ChatMessage lists should be forwarded (only TurnToken)
        List<ChatMessage> forwardedMessages = testContext.QueuedMessages[executor.Id]
            .Select(e => e.Message)
            .OfType<List<ChatMessage>>()
            .SelectMany(list => list)
            .ToList();

        Assert.Empty(forwardedMessages ?? []);
    }

    #endregion
}
