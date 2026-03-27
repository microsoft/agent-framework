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
/// A simple agent that emits a FunctionCallContent or ToolApprovalRequestContent request.
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
    /// or <see cref="ToolApprovalResponseContent"/>.  This models realistic agent behaviour
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
            c is FunctionResultContent || c is ToolApprovalResponseContent)))
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

internal sealed class KickoffOnStartExecutor : ChatProtocolExecutor
{
    private static readonly ChatProtocolExecutorOptions s_options = new()
    {
        AutoSendTurnToken = false,
    };

    private readonly string _downstreamExecutorId;
    private readonly string _kickoffInputText;
    private readonly string _kickoffMessageText;
    private readonly string _regularResumeText;
    private readonly string _regularProcessedText;

    public KickoffOnStartExecutor(
        string id,
        string downstreamExecutorId,
        string kickoffInputText,
        string kickoffMessageText,
        string regularResumeText,
        string regularProcessedText)
        : base(id, s_options)
    {
        this._downstreamExecutorId = downstreamExecutorId;
        this._kickoffInputText = kickoffInputText;
        this._kickoffMessageText = kickoffMessageText;
        this._regularResumeText = regularResumeText;
        this._regularProcessedText = regularProcessedText;
    }

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        List<string> textContents =
        [
            .. messages
                .SelectMany(message => message.Contents.OfType<TextContent>())
                .Select(content => content.Text)
        ];

        if (textContents.Contains(this._kickoffInputText, StringComparer.Ordinal))
        {
            await context.SendMessageAsync(
                new List<ChatMessage> { new(ChatRole.User, this._kickoffMessageText) },
                this._downstreamExecutorId,
                cancellationToken).ConfigureAwait(false);
            await context.SendMessageAsync(
                new TurnToken(emitEvents),
                this._downstreamExecutorId,
                cancellationToken).ConfigureAwait(false);
        }

        if (textContents.Contains(this._regularResumeText, StringComparer.Ordinal))
        {
            AgentResponseUpdate update = new(ChatRole.Assistant, [new TextContent(this._regularProcessedText)])
            {
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
                ResponseId = Guid.NewGuid().ToString("N"),
                Role = ChatRole.Assistant,
            };

            await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
        }
    }
}

/// <summary>
/// A start executor that always emits a response update on every turn,
/// useful for verifying that a TurnToken was delivered by the session.
/// On the first turn (user messages present), it kicks off a downstream executor.
/// </summary>
internal sealed class TurnTrackingStartExecutor : ChatProtocolExecutor
{
    private static readonly ChatProtocolExecutorOptions s_options = new()
    {
        AutoSendTurnToken = false,
    };

    private readonly string _downstreamExecutorId;
    private readonly string _activatedMarker;
    private int _activationCount;

    /// <summary>Gets the number of times this executor has been activated (i.e., <see cref="TakeTurnAsync"/> called).</summary>
    public int ActivationCount => this._activationCount;

    public TurnTrackingStartExecutor(string id, string downstreamExecutorId, string activatedMarker)
        : base(id, s_options)
    {
        this._downstreamExecutorId = downstreamExecutorId;
        this._activatedMarker = activatedMarker;
    }

    protected override async ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
    {
        Interlocked.Increment(ref this._activationCount);

        // On the first turn, forward user messages and a TurnToken to the downstream executor.
        if (messages.Any(m => m.Role == ChatRole.User))
        {
            await context.SendMessageAsync(
                messages,
                this._downstreamExecutorId,
                cancellationToken).ConfigureAwait(false);
            await context.SendMessageAsync(
                new TurnToken(emitEvents),
                this._downstreamExecutorId,
                cancellationToken).ConfigureAwait(false);
        }

        // Always emit a marker to prove this executor was activated.
        AgentResponseUpdate update = new(ChatRole.Assistant, [new TextContent(this._activatedMarker)])
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
            ResponseId = Guid.NewGuid().ToString("N"),
            Role = ChatRole.Assistant,
        };

        await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);
    }
}

public class WorkflowHostSmokeTests : AIAgentHostingExecutorTestsBase
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
            u.RawRepresentation is RequestInfoEvent && u.Contents.Any(c => c is FunctionCallContent));

        updateWithFunctionCall.Should().NotBeNull("a FunctionCallContent should be present in the response updates");
        FunctionCallContent retrievedContent = updateWithFunctionCall!.Contents
            .OfType<FunctionCallContent>()
            .Should().ContainSingle()
            .Which;

        retrievedContent.CallId.Should().NotBe(CallId);
        retrievedContent.CallId.Should().EndWith($":{CallId}");
        retrievedContent.Name.Should().Be(FunctionName);
    }

    /// <summary>
    /// Tests that when a workflow emits a RequestInfoEvent with ToolApprovalRequestContent data,
    /// the AgentResponseUpdate preserves the original ToolApprovalRequestContent type.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_ToolApprovalRequestContentPreservedInRequestInfoAsync()
    {
        // Arrange
        const string RequestId = "test-request-id";
        McpServerToolCallContent mcpCall = new("call-id", "testToolName", "http://localhost");
        ToolApprovalRequestContent originalContent = new(RequestId, mcpCall);
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
            u.RawRepresentation is RequestInfoEvent && u.Contents.Any(c => c is ToolApprovalRequestContent));

        updateWithUserInput.Should().NotBeNull("a ToolApprovalRequestContent should be present in the response updates");
        ToolApprovalRequestContent retrievedContent = updateWithUserInput!.Contents
            .OfType<ToolApprovalRequestContent>()
            .Should().ContainSingle()
            .Which;

        retrievedContent.Should().NotBeNull();
        retrievedContent.RequestId.Should().NotBe(RequestId);
        retrievedContent.RequestId.Should().EndWith($":{RequestId}");
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
            u.RawRepresentation is RequestInfoEvent && u.Contents.Any(c => c is FunctionCallContent));
        updateWithRequest.Should().NotBeNull("a FunctionCallContent should be present in the response updates");

        FunctionCallContent receivedRequest = updateWithRequest!.Contents
            .OfType<FunctionCallContent>()
            .First();
        receivedRequest.CallId.Should().EndWith($":{CallId}");

        // Act 2: Send the response back
        FunctionResultContent responseContent = new(receivedRequest.CallId, "test result");
        ChatMessage responseMessage = new(ChatRole.Tool, [responseContent]);

        // Act 2: Run the workflow with the response and capture the resulting updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be processed and the original request should no longer be pending.
        // Concretely, the workflow should not re-emit a FunctionCallContent with the same CallId.
        secondCallUpdates.Should().NotBeNull("processing the response should produce updates");
        secondCallUpdates.Should().NotBeEmpty("processing the response should progress the workflow");
        secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == receivedRequest.CallId, "the external FunctionCallContent request should be cleared after processing the response");
    }

    /// <summary>
    /// Tests the full roundtrip for ToolApprovalRequestContent: workflow emits request, external caller responds.
    /// Verifying inbound ToolApprovalResponseContent conversion.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_ToolApprovalRoundtrip_ResponseIsProcessedAsync()
    {
        // Arrange: Create an agent that emits a ToolApprovalRequestContent request
        const string RequestId = "roundtrip-request-id";
        McpServerToolCallContent mcpCall = new("mcp-call-id", "testMcpTool", "http://localhost");
        ToolApprovalRequestContent requestContent = new(RequestId, mcpCall);
        RequestEmittingAgent requestAgent = new(requestContent, completeOnResponse: true);
        ExecutorBinding agentBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUserInputRequests = false, EmitAgentUpdateEvents = true });
        Workflow workflow = new WorkflowBuilder(agentBinding).Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        // Act 1: First call - should receive the ToolApprovalRequestContent request
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, "Start"),
            session).ToListAsync();

        // Assert 1: We should have received a ToolApprovalRequestContent
        AgentResponseUpdate? updateWithRequest = firstCallUpdates.FirstOrDefault(u =>
            u.RawRepresentation is RequestInfoEvent && u.Contents.Any(c => c is ToolApprovalRequestContent));
        updateWithRequest.Should().NotBeNull("a ToolApprovalRequestContent should be present in the response updates");

        ToolApprovalRequestContent receivedRequest = updateWithRequest!.Contents
            .OfType<ToolApprovalRequestContent>()
            .First();
        receivedRequest.RequestId.Should().EndWith($":{RequestId}");

        // Act 2: Send the response back - use CreateResponse to get the right response type
        ToolApprovalResponseContent responseContent = receivedRequest.CreateResponse(approved: true);
        ChatMessage responseMessage = new(ChatRole.User, [responseContent]);

        // Act 2: Run the workflow again with the response and capture the updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be applied so that the original request is no longer pending
        secondCallUpdates.Should().NotBeEmpty("handling the user input response should produce follow-up updates");
        bool requestStillPresent = secondCallUpdates.Any(u =>
            u.RawRepresentation is RequestInfoEvent
            && u.Contents.OfType<ToolApprovalRequestContent>().Any(r => r.RequestId == receivedRequest.RequestId));
        requestStillPresent.Should().BeFalse("the original ToolApprovalRequestContent should not be re-emitted after its response is processed");
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
        AgentResponseUpdate requestUpdate = firstCallUpdates.First(u =>
            u.RawRepresentation is RequestInfoEvent && u.Contents.Any(c => c is FunctionCallContent));
        FunctionCallContent emittedRequest = requestUpdate.Contents.OfType<FunctionCallContent>().Single();

        firstCallUpdates.Should().Contain(u => u.Contents.Any(c => c is FunctionCallContent),
            "the first call should emit a FunctionCallContent request");

        // Act 2: Send a mixed message containing both the function result AND regular non-response content
        FunctionResultContent responseContent = new(emittedRequest.CallId, "tool output");
        ChatMessage mixedMessage = new(ChatRole.Tool, [responseContent, new TextContent("additional context")]);

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(mixedMessage, session).ToListAsync();

        // Assert 2: The workflow should have processed both parts without errors
        secondCallUpdates.Should().NotBeEmpty("the mixed message should produce follow-up updates");
        secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == emittedRequest.CallId, "the external FunctionCallContent should be cleared after the response is processed");
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
        FunctionCallContent emittedRequest = firstCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Single();

        ChatMessage[] resumeMessages =
        [
            new(ChatRole.Tool, [new FunctionResultContent(emittedRequest.CallId, "tool output")]),
            new(ChatRole.Tool, [new TextContent("extra context in separate message")])
        ];

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(resumeMessages, session).ToListAsync();

        secondCallUpdates.Should().NotBeEmpty();
        secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == emittedRequest.CallId, "response+regular content split across messages should not re-emit the handled external request");
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
        FunctionCallContent emittedRequest = firstCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Single();

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent(emittedRequest.CallId, "tool output")]),
            session).ToListAsync();

        int functionCallCount = secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Count(c => c.CallId == emittedRequest.CallId);

        functionCallCount.Should().Be(1, "a matching external response should not trigger an extra TurnToken-driven turn");
    }

    [Fact]
    public async Task Test_AsAgent_MixedResponseAndRegularMessage_CrossExecutorStartExecutorIsReawakenedAsync()
    {
        const string StartExecutorId = "start-executor";
        const string KickoffInputText = "Start";
        const string KickoffMessageText = "kickoff downstream";
        const string ResumeRegularText = "resume regular";
        const string ResumeProcessedText = "regular message processed";
        const string CallId = "cross-executor-call-id";
        const string FunctionName = "crossExecutorFunction";

        RequestEmittingAgent requestAgent = new(new FunctionCallContent(CallId, FunctionName), completeOnResponse: true);
        ExecutorBinding requestBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });

        KickoffOnStartExecutor startExecutor = new(
            StartExecutorId,
            requestBinding.Id,
            KickoffInputText,
            KickoffMessageText,
            ResumeRegularText,
            ResumeProcessedText);
        ExecutorBinding startBinding = startExecutor.BindExecutor();

        Workflow workflow = new WorkflowBuilder(startBinding)
            .AddEdge<List<ChatMessage>>(startBinding, requestBinding, messages =>
                messages?.Any(message => message.Contents.OfType<TextContent>().Any(content => content.Text == KickoffMessageText)) == true)
            .AddEdge<TurnToken>(startBinding, requestBinding, _ => true)
            .Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, KickoffInputText),
            session).ToListAsync();
        FunctionCallContent emittedRequest = firstCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Single();

        ChatMessage[] resumeMessages =
        [
            new(ChatRole.Tool, [new FunctionResultContent(emittedRequest.CallId, "tool output")]),
            new(ChatRole.User, ResumeRegularText)
        ];

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(resumeMessages, session).ToListAsync();
        List<string> textContents = [.. secondCallUpdates.SelectMany(update => update.Contents.OfType<TextContent>()).Select(content => content.Text)];

        textContents.Should().Contain(ResumeProcessedText, "the start executor should receive an explicit TurnToken when the matched response wakes a different executor");
        textContents.Should().Contain("Request processed", "the matched external response should still be delivered to the downstream request owner");
        secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Should()
            .NotContain(c => c.CallId == emittedRequest.CallId, "the handled external request should not be re-emitted while waking the start executor");
        secondCallUpdates.SelectMany(u => u.Contents.OfType<ErrorContent>()).Should().BeEmpty();
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

    /// <summary>
    /// Tests that when a resume contains only an external response directed at a non-start executor
    /// (no regular messages), the start executor still receives a TurnToken and is activated.
    /// This is a regression test for the case where the TurnToken was previously skipped because
    /// <c>HasRegularMessages</c> was <see langword="false"/>, leaving the start executor dormant.
    /// </summary>
    [Fact]
    public async Task Test_AsAgent_ResponseOnlyToNonStartExecutor_StartExecutorIsStillActivatedAsync()
    {
        // Arrange
        const string StartExecutorId = "start-executor";
        const string ActivatedMarker = "start-executor-activated";
        const string CallId = "response-only-call-id";
        const string FunctionName = "responseOnlyFunction";

        RequestEmittingAgent requestAgent = new(new FunctionCallContent(CallId, FunctionName), completeOnResponse: true);
        ExecutorBinding requestBinding = requestAgent.BindAsExecutor(
            new AIAgentHostOptions { InterceptUnterminatedFunctionCalls = false, EmitAgentUpdateEvents = true });

        TurnTrackingStartExecutor startExecutor = new(StartExecutorId, requestBinding.Id, ActivatedMarker);
        ExecutorBinding startBinding = startExecutor.BindExecutor();

        Workflow workflow = new WorkflowBuilder(startBinding)
            .AddEdge<List<ChatMessage>>(startBinding, requestBinding, messages =>
                messages?.Any(m => m.Contents.OfType<TextContent>().Any()) == true)
            .AddEdge<TurnToken>(startBinding, requestBinding, _ => true)
            .Build();
        AIAgent agent = workflow.AsAIAgent("WorkflowAgent");

        // Act 1: First call triggers the downstream FunctionCallContent request
        AgentSession session = await agent.CreateSessionAsync();
        List<AgentResponseUpdate> firstCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.User, "Start"),
            session).ToListAsync();

        FunctionCallContent emittedRequest = firstCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Single();

        // Act 2: Resume with ONLY the external response (no regular messages)
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent(emittedRequest.CallId, "tool output")]),
            session).ToListAsync();

        // Assert: Both the downstream and start executor should have been activated
        List<string> textContents = [.. secondCallUpdates
            .SelectMany(u => u.Contents.OfType<TextContent>())
            .Select(c => c.Text)];

        textContents.Should().Contain("Request processed",
            "the downstream executor should process the external response");
        textContents.Should().Contain(ActivatedMarker,
            "the start executor should receive a TurnToken and be activated even when resume contains only an external response");
        secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>())
            .Should()
            .BeEmpty();
    }

    private async Task Run_AsAgent_OutgoingMessagesInHistoryAsync(Workflow workflow, bool runAsync)
    {
        // Arrange
        AIAgent workflowAgent = workflow.AsAIAgent();

        // Act
        AgentSession session = await workflowAgent.CreateSessionAsync();
        AgentResponse response;
        if (runAsync)
        {
            List<AgentResponseUpdate> updates = [];
            await foreach (AgentResponseUpdate update in workflowAgent.RunStreamingAsync(session))
            {
                // Skip WorkflowEvent updates, which do not get persisted in ChatHistory; we cannot skip
                // them after because of a deleterious interaction with .ToAgentResponse() due to the
                // empty initial message (which is created without a MessageId). When running through the
                // message merger, it does the right thing internally.
                if (!string.IsNullOrEmpty(update.Text))
                {
                    updates.Add(update);
                }
            }

            response = updates.ToAgentResponse();
        }
        else
        {
            response = await workflowAgent.RunAsync(session);
        }

        // Assert
        WorkflowSession workflowSession = session.Should().BeOfType<WorkflowSession>().Subject;

        ChatMessage[] responseMessages = response.Messages.Where(message => message.Contents.Any())
                                                          .ToArray();

        ChatMessage[] sessionMessages = workflowSession.ChatHistoryProvider.GetAllMessages(workflowSession)
                                                                           .ToArray();

        // Since we never sent an incoming message, the expectation is that there should be nothing in the session
        // except the response
        responseMessages.Should().BeEquivalentTo(sessionMessages, options => options.WithStrictOrdering());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public Task Test_SingleAgent_AsAgent_OutgoingMessagesInHistoryAsync(bool runAsync)
    {
        // Arrange
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        Workflow singleAgentWorkflow = new WorkflowBuilder(agent).Build();
        return this.Run_AsAgent_OutgoingMessagesInHistoryAsync(singleAgentWorkflow, runAsync);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public Task Test_Handoffs_AsAgent_OutgoingMessagesInHistoryAsync(bool runAsync)
    {
        // Arrange
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);
        Workflow handoffWorkflow = new HandoffWorkflowBuilder(agent).Build();
        return this.Run_AsAgent_OutgoingMessagesInHistoryAsync(handoffWorkflow, runAsync);
    }
}
