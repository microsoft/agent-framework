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

    public RequestEmittingAgent(AIContent requestContent)
    {
        this._requestContent = requestContent;
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
        // Emit the request content
        yield return new AgentResponseUpdate(ChatRole.Assistant, [this._requestContent]);
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
        McpServerToolCallContent mcpCalll = new("call-id", "testToolName", "http://localhost");
        UserInputRequestContent originalContent = new McpServerToolApprovalRequestContent(RequestId, mcpCalll);
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
        RequestEmittingAgent requestAgent = new(requestContent);
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

        // This should work without throwing - the response should be converted to ExternalResponse
        // and processed by the workflow
        Func<Task> sendResponse = () => agent.RunStreamingAsync(responseMessage, session).ToListAsync().AsTask();

        // Assert 2: The response should be accepted without error
        await sendResponse.Should().NotThrowAsync("the response should be converted to ExternalResponse and processed");
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
        RequestEmittingAgent requestAgent = new(requestContent);
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

        // This should work without throwing - the response should be converted to ExternalResponse
        // and processed by the workflow
        Func<Task> sendResponse = () => agent.RunStreamingAsync(responseMessage, session).ToListAsync().AsTask();

        // Assert 2: The response should be accepted without error
        await sendResponse.Should().NotThrowAsync("the response should be converted to ExternalResponse and processed");
    }
}
