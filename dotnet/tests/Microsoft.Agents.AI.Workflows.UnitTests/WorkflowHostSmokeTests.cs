// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
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

public class NonChatProtocolExecutor() : Executor<string>(nameof(NonChatProtocolExecutor))
{
    public override ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return default;
    }
}

internal sealed class UppercaseStringExecutor(string name = "UppercaseStringExecutor") : Executor<IList<ChatMessage>, string>(name)
{
    public override ValueTask<string> HandleAsync(
        IList<ChatMessage> message,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        string text = string.Join(
            "\n",
            message.Select(chatMessage => chatMessage.Text).Where(text => !string.IsNullOrWhiteSpace(text)));
        return new(text.ToUpperInvariant());
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
                ErrorContent errorContent = Assert.IsType<ErrorContent>(Assert.Single(update.Contents));
                Assert.Equal(expectedMessage, errorContent.Message);
                hadErrorContent = true;
            }
        }

        Assert.True(hadErrorContent);
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

        Assert.NotNull(updateWithFunctionCall);
        FunctionCallContent retrievedContent = Assert.Single(updateWithFunctionCall!.Contents
            .OfType<FunctionCallContent>());

        Assert.NotEqual(CallId, retrievedContent.CallId);
        Assert.EndsWith($":{CallId}", retrievedContent.CallId);
        Assert.Equal(FunctionName, retrievedContent.Name);
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

        Assert.NotNull(updateWithUserInput);
        ToolApprovalRequestContent retrievedContent = Assert.Single(updateWithUserInput!.Contents
            .OfType<ToolApprovalRequestContent>());

        Assert.NotNull(retrievedContent);
        Assert.NotEqual(RequestId, retrievedContent.RequestId);
        Assert.EndsWith($":{RequestId}", retrievedContent.RequestId);
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
        Assert.NotNull(updateWithRequest);

        FunctionCallContent receivedRequest = updateWithRequest!.Contents
            .OfType<FunctionCallContent>()
            .First();
        Assert.EndsWith($":{CallId}", receivedRequest.CallId);

        // Act 2: Send the response back
        FunctionResultContent responseContent = new(receivedRequest.CallId, "test result");
        ChatMessage responseMessage = new(ChatRole.Tool, [responseContent]);

        // Act 2: Run the workflow with the response and capture the resulting updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be processed and the original request should no longer be pending.
        // Concretely, the workflow should not re-emit a FunctionCallContent with the same CallId.
        Assert.NotNull(secondCallUpdates);
        Assert.NotEmpty(secondCallUpdates);
        Assert.DoesNotContain(secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>()), c => c.CallId == receivedRequest.CallId);
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
        Assert.NotNull(updateWithRequest);

        ToolApprovalRequestContent receivedRequest = updateWithRequest!.Contents
            .OfType<ToolApprovalRequestContent>()
            .First();
        Assert.EndsWith($":{RequestId}", receivedRequest.RequestId);

        // Act 2: Send the response back - use CreateResponse to get the right response type
        ToolApprovalResponseContent responseContent = receivedRequest.CreateResponse(approved: true);
        ChatMessage responseMessage = new(ChatRole.User, [responseContent]);

        // Act 2: Run the workflow again with the response and capture the updates
        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(responseMessage, session).ToListAsync();

        // Assert 2: The response should be applied so that the original request is no longer pending
        Assert.NotEmpty(secondCallUpdates);
        bool requestStillPresent = secondCallUpdates.Any(u =>
            u.RawRepresentation is RequestInfoEvent
            && u.Contents.OfType<ToolApprovalRequestContent>().Any(r => r.RequestId == receivedRequest.RequestId));
        Assert.False(requestStillPresent);
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

        Assert.Contains(firstCallUpdates, u => u.Contents.Any(c => c is FunctionCallContent));

        // Act 2: Send a mixed message containing both the function result AND regular non-response content
        FunctionResultContent responseContent = new(emittedRequest.CallId, "tool output");
        ChatMessage mixedMessage = new(ChatRole.Tool, [responseContent, new TextContent("additional context")]);

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(mixedMessage, session).ToListAsync();

        // Assert 2: The workflow should have processed both parts without errors
        Assert.NotEmpty(secondCallUpdates);
        Assert.DoesNotContain(secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>()), c => c.CallId == emittedRequest.CallId);
        Assert.Empty(secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>()) ?? []);
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

        Assert.NotEmpty(secondCallUpdates);
        Assert.DoesNotContain(secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>()), c => c.CallId == emittedRequest.CallId);
        Assert.Empty(secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>()) ?? []);
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

        Assert.Equal(1, functionCallCount);
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

        Assert.Contains(ResumeProcessedText, textContents);
        Assert.Contains("Request processed", textContents);
        Assert.DoesNotContain(secondCallUpdates
            .Where(u => u.RawRepresentation is RequestInfoEvent)
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>()), c => c.CallId == emittedRequest.CallId);
        Assert.Empty(secondCallUpdates.SelectMany(u => u.Contents.OfType<ErrorContent>()) ?? []);
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
        Assert.Contains(firstCallUpdates, u => u.Contents.Any(c => c is FunctionCallContent));

        List<AgentResponseUpdate> secondCallUpdates = await agent.RunStreamingAsync(
            new ChatMessage(ChatRole.Tool, [new FunctionResultContent("different-call-id", "tool output")]),
            session).ToListAsync();

        int functionCallCount = secondCallUpdates
            .SelectMany(u => u.Contents.OfType<FunctionCallContent>())
            .Count(c => c.CallId == CallId);

        Assert.Equal(1, functionCallCount);
        Assert.Empty(secondCallUpdates.SelectMany(u => u.Contents.OfType<ErrorContent>()) ?? []);
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

        Assert.Contains("Request processed", textContents);
        Assert.Contains(ActivatedMarker, textContents);
        Assert.Empty(secondCallUpdates
            .SelectMany(u => u.Contents.OfType<ErrorContent>()) ?? []);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Test_AsAgent_FailsWhenNotChatProtocolAsync(bool runAsync)
    {
        // Arrange
        NonChatProtocolExecutor executor = new();
        Assert.False(executor.DescribeProtocol().IsChatProtocol());

        Workflow workflow = new WorkflowBuilder(executor).Build();
        AIAgent workflowAsAgent = workflow.AsAIAgent();

        Func<Task> action = runAsync
                          ? () => workflowAsAgent.RunStreamingAsync().ToAgentResponseAsync()
                          : () => workflowAsAgent.RunAsync();

        await Assert.ThrowsAsync<InvalidOperationException>(action);
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
        WorkflowSession workflowSession = Assert.IsType<WorkflowSession>(session);

        ChatMessage[] responseMessages = response.Messages.Where(message => message.Contents.Any())
                                                          .ToArray();

        ChatMessage[] sessionMessages = workflowSession.ChatHistoryProvider.GetAllMessages(workflowSession)
                                                                           .ToArray();

        // Since we never sent an incoming message, the expectation is that there should be nothing in the session
        // except the response
        Assert.Equivalent(sessionMessages, responseMessages);
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

    [Fact]
    public async Task Test_AsAgent_UsesDesignatedWorkflowOutputInsteadOfIntermediateAgentResponsesAsync()
    {
        TestReplayAgent firstAgent = new(TestReplayAgent.ToChatMessages("first answer"), "first-agent", "First Agent");
        TestReplayAgent secondAgent = new(TestReplayAgent.ToChatMessages("second answer"), "second-agent", "Second Agent");
        ExecutorBinding first = firstAgent.BindAsExecutor(new AIAgentHostOptions { ForwardIncomingMessages = false });
        ExecutorBinding second = secondAgent.BindAsExecutor(new AIAgentHostOptions { ForwardIncomingMessages = false });
        UppercaseStringExecutor uppercase = new();

        Workflow workflow = new WorkflowBuilder(first)
            .AddEdge(first, second)
            .AddEdge(second, uppercase)
            .WithOutputFrom(uppercase)
            .Build();

        AgentResponse response = await workflow
            .AsAIAgent("WorkflowAgent")
            .RunAsync(new ChatMessage(ChatRole.User, "hello"));

        Assert.Equal("SECOND ANSWER", response.Text);
        Assert.Equal("SECOND ANSWER", Assert.Single(response.Messages).Text);
    }

    // ----- Phase 5: Workflow-as-Agent intermediate forwarding -----------------

    [Collection(Futures.FuturesSerialCollection.Name)]
    public class IntermediateForwarding
    {
        private const string InterText = "progress";
        private const string FinalText = "final";

        private static async Task<List<AgentResponseUpdate>> RunStreamingAsync(
            Workflow workflow,
            bool includeWorkflowOutputsInResponse = false)
        {
            return await workflow
                .AsAIAgent("WorkflowAgent", includeWorkflowOutputsInResponse: includeWorkflowOutputsInResponse)
                .RunStreamingAsync(new ChatMessage(ChatRole.User, "hi"))
                .ToListAsync();
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_IntermediateAgentResponseForwardedInStreamingAsync()
        {
            using Futures.FuturesScope _ = new(enabled: true);
            TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(InterText));
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            Workflow workflow = new WorkflowBuilder(binding)
                .WithIntermediateOutputFrom([binding])
                .Build();

            // Under Futures-on, AgentResponseEvent mirrors AgentResponseUpdateEvent: always
            // forwarded regardless of the include flag. The intermediate tag is observable on
            // the surfaced event for consumers that care to distinguish.
            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: false);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent are && are.IsIntermediate() && u.Contents.Count == 0);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_TerminalAgentResponseForwardedUnconditionallyWhenFuturesOnAsync()
        {
            using Futures.FuturesScope _ = new(enabled: true);
            TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(FinalText));
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            Workflow workflow = new WorkflowBuilder(binding)
                .WithOutputFrom(binding)
                .Build();

            // Even a terminal-only designation surfaces without the include flag — the gating
            // asymmetry between AgentResponse and AgentResponseUpdate is gone under Futures-on.
            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: false);

            Assert.Equal(1, updates.Count(u => u.Text == FinalText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Contents.Count == 0);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_EmptyAgentResponseDoesNotCreateObservabilityUpdateAsync()
        {
            using Futures.FuturesScope _ = new(enabled: true);
            TestReplayAgent agent = new(new List<ChatMessage>());
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            Workflow workflow = new WorkflowBuilder(binding)
                .WithOutputFrom(binding)
                .Build();

            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: false);

            Assert.DoesNotContain(updates, u => u.RawRepresentation is AgentResponseEvent);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_TerminalAgentResponseGatedWhenFuturesOffAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);

            static Workflow Build()
            {
                TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(FinalText));
                ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
                return new WorkflowBuilder(binding).WithOutputFrom(binding).Build();
            }

            // Legacy semantics: AgentResponseEvent stays behind the include flag when Futures
            // is off. Two fresh workflows because in-process runs aren't reentrant.
            List<AgentResponseUpdate> gated = await RunStreamingAsync(Build(), includeWorkflowOutputsInResponse: false);
            Assert.DoesNotContain(gated, u => u.RawRepresentation is AgentResponseEvent && u.Text == FinalText);

            List<AgentResponseUpdate> included = await RunStreamingAsync(Build(), includeWorkflowOutputsInResponse: true);
            Assert.Equal(1, included.Count(u => u.Text == FinalText));
            Assert.Contains(included, u => u.RawRepresentation is AgentResponseEvent && u.Contents.Count == 0);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_UndesignatedExecutorEmitsNoAgentResponseEventWhenFuturesOnAsync()
        {
            using Futures.FuturesScope _ = new(enabled: true);
            TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(InterText));
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            // No designation — under Futures-on, the AgentResponse is dropped by the filter.
            Workflow workflow = new WorkflowBuilder(binding).Build();

            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.DoesNotContain(updates, u => u.RawRepresentation is AgentResponseEvent);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_UndesignatedAgentResponseSurfacesWhenFuturesOffAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);
            TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(InterText));
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            Workflow workflow = new WorkflowBuilder(binding).Build();

            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Contents.Count == 0);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_IntermediateTagAvailableViaRawRepresentationAsync()
        {
            using Futures.FuturesScope _ = new(enabled: true);
            TestReplayAgent agent = new(TestReplayAgent.ToChatMessages(InterText));
            ExecutorBinding binding = agent.BindAsExecutor(new AIAgentHostOptions { EmitAgentResponseEvents = true });
            Workflow workflow = new WorkflowBuilder(binding)
                .WithIntermediateOutputFrom([binding])
                .Build();

            List<AgentResponseUpdate> updates = await RunStreamingAsync(workflow);

            AgentResponseUpdate progress = updates.First(u => u.RawRepresentation is AgentResponseEvent);
            AgentResponseEvent raw = (AgentResponseEvent)progress.RawRepresentation!;
            Assert.True(raw.IsIntermediate());
            Assert.Equivalent(new[] { OutputTag.Intermediate }, raw.Tags);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_DistinctCompletedResponseFromSameExecutorIsForwardedAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);
            Workflow workflow = new WorkflowBuilder(new StreamThenCompleteExecutor()).Build();

            List<AgentResponseUpdate> updates =
                await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Equal(1, updates.Count(u => u.Text == FinalText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Text == FinalText);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_DistinctCompletedMessageFromSameResponseIsForwardedAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);
            Workflow workflow = new WorkflowBuilder(new StreamThenCompleteExecutor(useSameResponseId: true)).Build();

            List<AgentResponseUpdate> updates =
                await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Equal(1, updates.Count(u => u.Text == FinalText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Text == FinalText);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_WhitespaceMessageIdDoesNotSuppressCompletionAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);
            Workflow workflow =
                new WorkflowBuilder(
                    new StreamThenCompleteExecutor(
                        useSameResponseId: true,
                        streamedMessageId: " ",
                        completedMessageId: " "))
                .Build();

            List<AgentResponseUpdate> updates =
                await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Equal(1, updates.Count(u => u.Text == FinalText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Text == FinalText);
        }

        [Fact]
        public async Task Test_WorkflowHostAgent_UnstreamedMessageFromSameResponseIsForwardedAsync()
        {
            using Futures.FuturesScope _ = new(enabled: false);
            Workflow workflow = new WorkflowBuilder(new PartiallyStreamedResponseExecutor()).Build();

            List<AgentResponseUpdate> updates =
                await RunStreamingAsync(workflow, includeWorkflowOutputsInResponse: true);

            Assert.Equal(1, updates.Count(u => u.Text == InterText));
            Assert.Equal(1, updates.Count(u => u.Text == FinalText));
            Assert.Contains(updates, u => u.RawRepresentation is AgentResponseEvent && u.Text == FinalText);
        }

        private sealed class StreamThenCompleteExecutor(
            bool useSameResponseId = false,
            string streamedMessageId = "streamed-message",
            string completedMessageId = "completed-message") : Executor("stream-then-complete")
        {
            protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
                protocolBuilder.ConfigureRoutes(
                    routeBuilder =>
                        routeBuilder
                            .AddHandler<IEnumerable<ChatMessage>>(this.HandleMessagesAsync)
                            .AddHandler<TurnToken, AgentResponse>(this.HandleTurnAsync));

            private ValueTask HandleMessagesAsync(
                IEnumerable<ChatMessage> messages,
                IWorkflowContext context,
                CancellationToken cancellationToken) => default;

            private async ValueTask<AgentResponse> HandleTurnAsync(
                TurnToken turnToken,
                IWorkflowContext context,
                CancellationToken cancellationToken)
            {
                AgentResponseUpdate update =
                    new(ChatRole.Assistant, InterText)
                    {
                        MessageId = streamedMessageId,
                        ResponseId = "streamed-response",
                    };
                await context.AddEventAsync(
                    new AgentResponseUpdateEvent(this.Id, update),
                    cancellationToken);

                ChatMessage message =
                    new(ChatRole.Assistant, FinalText)
                    {
                        MessageId = completedMessageId,
                    };
                return new AgentResponse([message])
                {
                    ResponseId = useSameResponseId ? update.ResponseId : "completed-response",
                };
            }
        }

        private sealed class PartiallyStreamedResponseExecutor() : Executor("partially-streamed-response")
        {
            protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
                protocolBuilder.ConfigureRoutes(
                    routeBuilder =>
                        routeBuilder
                            .AddHandler<IEnumerable<ChatMessage>>(this.HandleMessagesAsync)
                            .AddHandler<TurnToken, AgentResponse>(this.HandleTurnAsync));

            private ValueTask HandleMessagesAsync(
                IEnumerable<ChatMessage> messages,
                IWorkflowContext context,
                CancellationToken cancellationToken) => default;

            private async ValueTask<AgentResponse> HandleTurnAsync(
                TurnToken turnToken,
                IWorkflowContext context,
                CancellationToken cancellationToken)
            {
                const string ResponseId = "shared-response";
                ChatMessage streamedMessage =
                    new(ChatRole.Assistant, InterText)
                    {
                        MessageId = "streamed-message",
                    };
                AgentResponseUpdate streamedUpdate =
                    new(ChatRole.Assistant, InterText)
                    {
                        MessageId = streamedMessage.MessageId,
                        ResponseId = ResponseId,
                    };
                await context.AddEventAsync(
                    new AgentResponseUpdateEvent(
                        this.Id,
                        streamedUpdate),
                    cancellationToken);

                ChatMessage completedOnlyMessage =
                    new(ChatRole.Assistant, FinalText)
                    {
                        MessageId = "completed-only-message",
                    };
                return new AgentResponse([streamedMessage, completedOnlyMessage]) { ResponseId = ResponseId };
            }
        }
    }
}
