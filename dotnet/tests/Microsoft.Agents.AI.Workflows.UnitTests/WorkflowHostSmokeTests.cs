// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class ExpectedException : Exception
{
    public ExpectedException(string message)
        : base(message)
    {
    }

    public ExpectedException() : base()
    {
    }

    public ExpectedException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}

/// <summary>
/// A simple agent that emits a FunctionCallContent or UserInputRequestContent request.
/// Used to test that RequestInfoEvent handling preserves the original content type.
/// </summary>
internal sealed class RequestEmittingAgent : AIAgent
{
    private readonly AIContent _requestContent;
    private readonly bool _completeOnResponse;

    /// <summary>
    /// Creates a new <see cref="RequestEmittingAgent"/> that emits the given request content.
    /// </summary>
    /// <param name="requestContent">The content to emit on each turn.</param>
    /// <param name="completeOnResponse">
    /// When <see langword="true"/>, the agent emits a text completion instead of re-emitting
    /// the request when the incoming messages contain a <see cref="FunctionResultContent"/>
    /// or <see cref="UserInputResponseContent"/>.  This models realistic agent behaviour
    /// where the agent processes the tool result and produces a final answer.
    /// </param>
    public RequestEmittingAgent(AIContent requestContent, bool completeOnResponse = false)
    {
        this._requestContent = requestContent;
        this._completeOnResponse = completeOnResponse;
    }

    private sealed class Session : AgentSession
    {
        public Session() { }
    }

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(new Session());

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new Session());

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => default;

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._completeOnResponse && messages.Any(m => m.Contents.Any(c =>
            c is FunctionResultContent || c is UserInputResponseContent)))
        {
            yield return new AgentResponseUpdate(ChatRole.Assistant, [new TextContent("Request processed")]);
        }
        else
        {
            // Emit the request content
            yield return new AgentResponseUpdate(ChatRole.Assistant, [this._requestContent]);
        }
    }
}

public class WorkflowHostSmokeTests
{
    private sealed class AlwaysFailsAIAgent(bool failByThrowing) : AIAgent
    {
        private sealed class Session : AgentSession
        {
            public Session() { }

            public Session(AgentSessionStateBag stateBag) : base(stateBag) { }
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            return new(serializedState.Deserialize<Session>(jsonSerializerOptions)!);
        }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            return new(new Session());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override async Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            return await this.RunStreamingAsync(messages, session, options, cancellationToken)
                             .ToAgentResponseAsync(cancellationToken);
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            const string ErrorMessage = "Simulated agent failure.";
            if (failByThrowing)
            {
                throw new ExpectedException(ErrorMessage);
            }

            yield return new AgentResponseUpdate(ChatRole.Assistant, [new ErrorContent(ErrorMessage)]);
        }
    }

    private static Workflow CreateWorkflow(bool failByThrowing)
    {
        ExecutorBinding agent = new AlwaysFailsAIAgent(failByThrowing).BindAsExecutor(emitEvents: true);

        return new WorkflowBuilder(agent).Build();
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task Test_AsAgent_ErrorContentStreamedOutAsync(bool includeExceptionDetails, bool failByThrowing)
    {
        string expectedMessage = !failByThrowing || includeExceptionDetails
                               ? "Simulated agent failure."
                               : "An error occurred while executing the workflow.";

        // Arrange is done by the caller.
        Workflow workflow = CreateWorkflow(failByThrowing);

        // Act
        List<AgentResponseUpdate> updates = await workflow.AsAIAgent("WorkflowAgent", includeExceptionDetails: includeExceptionDetails)
                                                             .RunStreamingAsync(new ChatMessage(ChatRole.User, "Hello"))
                                                             .ToListAsync();

        // Assert
        bool hadErrorContent = false;
        foreach (AgentResponseUpdate update in updates)
        {
            if (update.Contents.Any())
            {
                // We should expect a single update which contains the error content.
                update.Contents.Should().ContainSingle()
                                        .Which.Should().BeOfType<ErrorContent>()
                                        .Which.Message.Should().Be(expectedMessage);
                hadErrorContent = true;
            }
        }

        hadErrorContent.Should().BeTrue();
    }

    /// <summary>
    /// Tests that when a workflow emits a RequestInfoEvent with FunctionCallContent data,
    /// the AgentResponseUpdate preserves the original FunctionCallContent type.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_FunctionCallContentPreservedInRequestInfoAsync()
    {
        // Arrange
        const string CallId = "test-call-id";
        const string FunctionName = "testFunction";
        FunctionCallContent originalContent = new(CallId, FunctionName);
        RequestEmittingAgent requestAgent = new(originalContent);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();

        // Act
        List<AgentResponseUpdate> updates = await workflow.AsAIAgent("WorkflowAgent")
                                                           .RunStreamingAsync(new ChatMessage(ChatRole.User, "Hello"))
                                                           .ToListAsync();

        // Assert
        AgentResponseUpdate? updateWithFunctionCall = updates.FirstOrDefault(u =>
            u.Contents.Any(c => c is FunctionCallContent));

        updateWithFunctionCall.Should().NotBeNull("a FunctionCallContent should be present in the response updates");
        FunctionCallContent retrievedContent = updateWithFunctionCall!.Contents
            .OfType<FunctionCallContent>()
            .Should().ContainSingle()
            .Which;

        retrievedContent.CallId.Should().Be(CallId);
        retrievedContent.Name.Should().Be(FunctionName);
    }

    /// <summary>
    /// Tests that when a workflow emits a RequestInfoEvent with UserInputRequestContent data,
    /// the AgentResponseUpdate preserves the original UserInputRequestContent type.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_UserInputRequestContentPreservedInRequestInfoAsync()
    {
        // Arrange
        const string RequestId = "test-request-id";
        McpServerToolCallContent mcpCall = new("call-id", "testToolName", "http://localhost");
        UserInputRequestContent originalContent = new McpServerToolApprovalRequestContent(RequestId, mcpCall);
        RequestEmittingAgent requestAgent = new(originalContent);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUserInputRequests = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();

        // Act
        List<AgentResponseUpdate> updates = await workflow.AsAIAgent("WorkflowAgent")
                                                           .RunStreamingAsync(new ChatMessage(ChatRole.User, "Hello"))
                                                           .ToListAsync();

        // Assert
        AgentResponseUpdate? updateWithUserInput = updates.FirstOrDefault(u =>
            u.Contents.Any(c => c is UserInputRequestContent));

        updateWithUserInput.Should().NotBeNull("a UserInputRequestContent should be present in the response updates");
        UserInputRequestContent retrievedContent = updateWithUserInput!.Contents
            .OfType<UserInputRequestContent>()
            .Should().ContainSingle()
            .Which;

        retrievedContent.Should().BeOfType<McpServerToolApprovalRequestContent>();
        retrievedContent.Id.Should().Be(RequestId);
    }

    /// <summary>
    /// Tests the full roundtrip: workflow emits a request, external caller responds, workflow processes response.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_FunctionCallRoundtrip_ResponseIsProcessedAsync()
    {
        // Arrange: Create an agent that emits a FunctionCallContent request
        const string CallId = "roundtrip-call-id";
        const string FunctionName = "testFunction";
        FunctionCallContent requestContent = new(CallId, FunctionName);
        RequestEmittingAgent requestAgent = new(requestContent, completeOnResponse: true);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        // Act 1: First call - should receive the FunctionCallContent request
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, "Start"),
            session).ToListAsync();

        // Assert 1: We should have received a FunctionCallContent
        AgentResponseUpdate? updateWithRequest = firstCallUpdates.FirstOrDefault(u =>
            u.Contents.Any(c => c is FunctionCallContent));
        updateWithRequest.Should().NotBeNull("a FunctionCallContent should be present in the response updates");

        FunctionCallContent receivedRequest = updateWithRequest!.Contents
            .OfType<FunctionCallContent>()
            .First();
        receivedRequest.CallId.Should().Be(CallId);

        // Act 2: Send the response back
        FunctionResultContent responseContent = new(CallId, "test result");
        ChatMessage responseMessage = new(ChatRole.Tool, [responseContent]);

        // Act 2: Run the workflow with the response and capture the resulting updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be processed and the original request should no longer be pending.
        // Concretely, the workflow should not re-emit a FunctionCallContent with the same CallId.
        secondCallUpdates.Should().NotBeNull("processing the response should produce updates");
        secondCallUpdates.Should().NotBeEmpty("processing the response should progress the workflow");
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == CallId, "the original FunctionCallContent request should be cleared after processing the response");
    }

    /// <summary>
    /// Tests the full roundtrip for UserInputRequestContent: workflow emits request, external caller responds.
    /// Verifying inbound UserInputResponseContent conversion.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_UserInputRoundtrip_ResponseIsProcessedAsync()
    {
        // Arrange: Create an agent that emits a UserInputRequestContent request
        const string RequestId = "roundtrip-request-id";
        McpServerToolCallContent mcpCall = new("mcp-call-id", "testMcpTool", "http://localhost");
        McpServerToolApprovalRequestContent requestContent = new(RequestId, mcpCall);
        RequestEmittingAgent requestAgent = new(requestContent, completeOnResponse: true);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUserInputRequests = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        // Act 1: First call - should receive the UserInputRequestContent request
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, "Start"),
            session).ToListAsync();

        // Assert 1: We should have received a UserInputRequestContent
        AgentResponseUpdate? updateWithRequest = firstCallUpdates.FirstOrDefault(u =>
            u.Contents.Any(c => c is UserInputRequestContent));
        updateWithRequest.Should().NotBeNull("a UserInputRequestContent should be present in the response updates");

        UserInputRequestContent receivedRequest = updateWithRequest!.Contents
            .OfType<UserInputRequestContent>()
            .First();
        receivedRequest.Id.Should().Be(RequestId);

        // Act 2: Send the response back - use CreateResponse to get the right response type
        UserInputResponseContent responseContent = requestContent.CreateResponse(approved: true);
        ChatMessage responseMessage = new(ChatRole.User, [responseContent]);

        // Act 2: Run the workflow again with the response and capture the updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be applied so that the original request is no longer pending
        secondCallUpdates.Should().NotBeEmpty("handling the user input response should produce follow-up updates");
        bool requestStillPresent = secondCallUpdates.Any(u => u.Contents.OfType<UserInputRequestContent>().Any(r => r.Id == RequestId));
        requestStillPresent.Should().BeFalse("the original UserInputRequestContent should not be re-emitted after its response is processed");
    }

    /// <summary>
    /// Tests the mixed-message scenario: resume contains both an external response
    /// (FunctionResultContent matching a pending request) and regular non-response content
    /// in the same message.
    /// Verifies that regular content is still processed and that no duplicate
    /// pending-request errors, redundant FunctionCallContent re-emissions,
    /// or workflow errors occur.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_MixedResponseAndRegularMessage_BothProcessedAsync()
    {
        // Arrange: Create an agent that emits a FunctionCallContent request
        const string CallId = "mixed-call-id";
        const string FunctionName = "mixedTestFunction";
        FunctionCallContent requestContent = new(CallId, FunctionName);
        RequestEmittingAgent requestAgent = new(requestContent, completeOnResponse: true);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        // Act 1: First call - should receive the FunctionCallContent request
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, "Start"),
            session).ToListAsync();

        // Assert 1: We should have received a FunctionCallContent
        firstCallUpdates.Should().Contain(u => u.Contents.Any(c => c is FunctionCallContent),
            "the first call should emit a FunctionCallContent request");

        // Act 2: Send a mixed message containing both the function result AND regular non-response content
        FunctionResultContent responseContent = new(CallId, "tool output");
        ChatMessage mixedMessage = new(ChatRole.Tool, [responseContent, new TextContent("additional context")]);

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(mixedMessage, session).ToListAsync();

        // Assert 2: The workflow should have processed both parts without errors
        secondCallUpdates.Should().NotBeEmpty("the mixed message should produce follow-up updates");
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == CallId, "the original FunctionCallContent should be cleared after the response is processed");
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>())
            .Should()
            .BeEmpty("no workflow errors should occur when processing a mixed response-and-regular message");
    }

    [Fact]
    public async Task Test_AsAgent_ResponseThenRegularAcrossMessages_NoDuplicateFunctionCallAsync()
    {
        const string CallId = "mixed-separate-call-id";
        const string FunctionName = "mixedSeparateTestFunction";

        RequestEmittingAgent requestAgent = new(new FunctionCallContent(CallId, FunctionName), completeOnResponse: true);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(new ChatMessage(ChatRole.User, "Start"), session).ToListAsync();
        firstCallUpdates.Should().Contain(u => u.Contents.Any(c => c is FunctionCallContent));

        ChatMessage[] resumeMessages =
        [
            new(ChatRole.Tool, [new FunctionResultContent(CallId, "tool output")]),
            new(ChatRole.Tool, [new TextContent("extra context in separate message")])
        ];

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(resumeMessages, session).ToListAsync();

        secondCallUpdates.Should().NotBeEmpty();
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == CallId, "response+regular content split across messages should not re-emit the handled request");
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>())
            .Should()
            .BeEmpty();
    }

    [Fact]
    public async Task Test_AsAgent_MatchingResponse_DoesNotCauseExtraTurnAsync()
    {
        const string CallId = "matching-response-call-id";
        const string FunctionName = "matchingResponseFunction";

        RequestEmittingAgent requestAgent = new(new FunctionCallContent(CallId, FunctionName), completeOnResponse: false);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(new ChatMessage(ChatRole.User, "Start"), session).ToListAsync();
        firstCallUpdates.Should().Contain(u => u.Contents.Any(c => c is FunctionCallContent));

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent(CallId, "tool output")]),
            session).ToListAsync();

        int functionCallCount = secondCallUpdates
            .Where(u => u.RawRepresentation?.GetType().Name == "RequestInfoEvent")
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Count(c => c.CallId == CallId);

        functionCallCount.Should().Be(1, "a matching external response should not trigger an extra TurnToken-driven turn");
    }

    [Fact]
    public async Task Test_AsAgent_UnmatchedResponse_TriggersTurnAndKeepsProgressingAsync()
    {
        const string CallId = "unmatched-response-call-id";
        const string FunctionName = "unmatchedResponseFunction";

        RequestEmittingAgent requestAgent = new(new FunctionCallContent(CallId, FunctionName), completeOnResponse: false);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(new ChatMessage(ChatRole.User, "Start"), session).ToListAsync();
        firstCallUpdates.Should().Contain(u => u.Contents.Any(c => c is FunctionCallContent));

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("different-call-id", "tool output")]),
            session).ToListAsync();

        int functionCallCount = secondCallUpdates
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Count(c => c.CallId == CallId);

        functionCallCount.Should().Be(1, "an unmatched response should be treated as regular input and still drive a TurnToken continuation without workflow errors");
        secondCallUpdates.SelectMany(u => u.Contents.OfType<ErrorContent>()).Should().BeEmpty();
    }
}
