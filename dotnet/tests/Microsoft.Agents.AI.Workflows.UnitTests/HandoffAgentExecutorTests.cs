// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Sample;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class HandoffAgentExecutorTests : AIAgentHostingExecutorTestsBase
{
    private sealed class AgentIdOverrideReplayAgent(
        FunctionCallContent content,
        string? updateAgentId,
        string? id = null,
        string? name = null) : TestReplayAgent(id, name)
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new AgentResponseUpdate(ChatRole.Assistant, [content])
            {
                AgentId = updateAgentId,
                MessageId = "nested-message",
                ResponseId = "nested-response",
            };
        }
    }

    private sealed class CancellableHandoffReplayAgent(string? id = null, string? name = null) : TestReplayAgent(id, name)
    {
        private int _invocation;

        public TaskCompletionSource<bool> FirstRequestObserved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (this._invocation++ == 0)
            {
                yield return new AgentResponseUpdate(
                    ChatRole.Assistant,
                    [new FunctionCallContent("cancelled-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1")])
                {
                    AgentId = this.Id,
                    MessageId = "cancelled-message",
                    ResponseId = "cancelled-response",
                };

                this.FirstRequestObserved.SetResult(true);
                await Task.Delay(Timeout.Infinite, cancellationToken);
            }
            else
            {
                yield return new AgentResponseUpdate(ChatRole.Assistant, "Completed without handoff.")
                {
                    AgentId = this.Id,
                    MessageId = "completed-message",
                    ResponseId = "completed-response",
                };
            }
        }
    }

    private sealed class StreamingUpdatesReplayAgent(
        IReadOnlyList<AgentResponseUpdate> updates,
        string? id = null,
        string? name = null) : TestReplayAgent(id, name)
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (AgentResponseUpdate update in updates)
            {
                await Task.Yield();
                yield return update;
            }
        }
    }

    private static async ValueTask<TestRunContext> PrepareHandoffSharedStateAsync(TestRunContext? runContext = null, IEnumerable<ChatMessage>? messages = null)
    {
        runContext ??= new();

        HandoffSharedState sharedState = new();

        if (messages != null)
        {
            sharedState.Conversation.AddMessages(messages);
        }

        await runContext.BindWorkflowContext(nameof(HandoffStartExecutor))
                        .QueueStateUpdateAsync(HandoffConstants.HandoffSharedStateKey,
                                               sharedState,
                                               HandoffConstants.HandoffSharedStateScope);

        await runContext.StateManager.PublishUpdatesAsync(null);

        return runContext;
    }

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
    public async Task Test_HandoffAgentExecutor_EmitsStreamingUpdatesIFFConfiguredAsync(bool? executorSetting, bool? turnSetting)
    {
        // Arrange
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: executorSetting,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, [], options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(turnSetting), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        bool expectingStreamingUpdates = turnSetting ?? executorSetting ?? false;

        AgentResponseUpdateEvent[] updates = testContext.Events.OfType<AgentResponseUpdateEvent>().ToArray();
        CheckResponseUpdateEventsAgainstTestMessages(updates, expectingStreamingUpdates, agent.GetDescriptiveId());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_HandoffAgentExecutor_EmitsResponseIFFConfiguredAsync(bool executorSetting)
    {
        // Arrange
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        TestReplayAgent agent = new(TestMessages, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: executorSetting,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(agent, [], options);
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(false), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        AgentResponseEvent[] updates = testContext.Events.OfType<AgentResponseEvent>().ToArray();
        CheckResponseEventsAgainstTestMessages(updates, expectingResponse: executorSetting, agent.GetDescriptiveId());
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_ComposesWithHITLSubworkflowAsync()
    {
        // Arrange
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();

        SendsRequestExecutor challengeSender = new();
        Workflow subworkflow = new WorkflowBuilder(challengeSender)
                                   .AddExternalRequest<Challenge, Response>(challengeSender, "SendChallengeToUser")
                                   .WithOutputFrom(challengeSender)
                                   .Build();

        InProcessExecutionEnvironment environment = InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory());
        AIAgent subworkflowAgent = subworkflow.AsAIAgent(includeWorkflowOutputsInResponse: true, name: "Subworkflow", executionEnvironment: environment);
        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: true,
                                                  emitAgentResponseUpdateEvents: true,
                                                  HandoffToolCallFilteringBehavior.None);

        HandoffAgentExecutor executor = new(subworkflowAgent, [], options);
        Workflow fakeWorkflow = new(executor.Id) { ExecutorBindings = { { executor.Id, executor } } };
        EdgeMap map = new(testContext, fakeWorkflow, null);

        testContext.ConfigureExecutor(executor, map);

        // Validate that our test assumptions hold
        string functionCallPortId = $"{HandoffAgentExecutor.IdFor(subworkflowAgent)}_FunctionCall";
        Assert.True(map.TryGetResponsePortExecutorId(functionCallPortId, out string? responsePortExecutorId));
        Assert.Equal(executor.Id, responsePortExecutorId);

        // Act
        HandoffState message = new(new(false), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        await testContext.StateManager.PublishUpdatesAsync(null);

        // Assert
        Assert.Single(testContext.ExternalRequests);
        Assert.Single(testContext.ExternalRequests, request => request.IsDataOfType<FunctionCallContent>());

        FunctionCallContent functionCallContent = testContext.ExternalRequests.Single().Data.As<FunctionCallContent>()!;
        object? requestData = functionCallContent.Arguments!["data"];

        Challenge? challenge = null;
        if (requestData is PortableValue pv)
        {
            challenge = pv.As<Challenge>();
        }
        else
        {
            challenge = requestData as Challenge;
        }

        if (challenge is null)
        {
            Assert.Fail($"Expected request data to be of type {typeof(Challenge).FullName}, but was {requestData?.GetType().FullName ?? "null"}");
            return; // Unreachable, but analysis cannot infer that Debug.Fail will throw/exit, and UnreachableException is not available on net472
        }

        // Act 2
        string challengeResponse = new(challenge.Value.Reverse().ToArray());
        FunctionResultContent responseContent = new(functionCallContent.CallId, new Response(challengeResponse));

        RequestPortInfo requestPortInfo = new(new(typeof(Challenge)), new(typeof(Response)), functionCallPortId);
        string requestId = $"{functionCallPortId.Length}:{functionCallPortId}:{functionCallContent.CallId}";
        DeliveryMapping? mapping = await map.PrepareDeliveryForResponseAsync(new(requestPortInfo, requestId, new(responseContent)));

        Assert.Single(mapping!.Deliveries);

        MessageDelivery delivery = mapping.Deliveries.Single();

        object? result = await executor.ExecuteCoreAsync(delivery.Envelope.Message,
                                                         delivery.Envelope.MessageType,
                                                         testContext.BindWorkflowContext(executor.Id));
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_PreservesExistingInstructionsAndToolsAsync()
    {
        // Arrange
        const string BaseInstructions = "BaseInstructions";
        const string HandoffInstructions = "HandoffInstructions";

        AITool someTool = AIFunctionFactory.CreateDeclaration("BaseTool", null, AIFunctionFactory.Create(() => { }).JsonSchema);

        OptionValidatingChatClient chatClient = new(BaseInstructions, HandoffInstructions, someTool);
        AIAgent handoffAgent = chatClient.AsAIAgent(BaseInstructions, tools: [someTool]);
        AIAgent targetAgent = new TestEchoAgent();

        HandoffAgentExecutorOptions options = new(HandoffInstructions, false, null, HandoffToolCallFilteringBehavior.None);
        HandoffTarget handoff = new(targetAgent);
        HandoffAgentExecutor executor = new(handoffAgent, [handoff], options);

        TestRunContext runContext = await PrepareHandoffSharedStateAsync();
        IWorkflowContext testContext = runContext.BindWorkflowContext(executor.Id);
        HandoffState state = new(new(false), null);

        // Act / Assert
        async Task runStreamingAsync() => await executor.HandleAsync(state, testContext);
        Assert.Null(await Record.ExceptionAsync(runStreamingAsync));
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotRouteCompletedHandoffNamedToolEventAsync()
    {
        // Arrange
        const string CallId = "provider-tool-call";
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent toolStart = new(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")
        {
            RawRepresentation = new object(),
        };
        FunctionResultContent toolComplete = new(CallId, "Tool execution failed")
        {
            RawRepresentation = new object(),
        };
        TestReplayAgent agent = new(
        [
            new ChatMessage(ChatRole.Assistant, [toolStart]) { MessageId = "provider-tool-start" },
            new ChatMessage(ChatRole.Tool, [toolComplete]) { MessageId = "provider-tool-complete" },
        ], TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        HandoffState message = new(new(false), null, null);
        await executor.HandleAsync(message, testContext.BindWorkflowContext(executor.Id));

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Null(sentState.RequestedHandoffTargetAgentId);

        HandoffSharedState? sharedState = await testContext
            .BindWorkflowContext(nameof(HandoffStartExecutor))
            .ReadStateAsync<HandoffSharedState>(
                HandoffConstants.HandoffSharedStateKey,
                HandoffConstants.HandoffSharedStateScope);
        Assert.NotNull(sharedState);
        Assert.DoesNotContain(
            sharedState.Conversation.History.SelectMany(history => history.Contents).OfType<FunctionResultContent>(),
            result => result.CallId == CallId && string.Equals(result.Result?.ToString(), "Transferred.", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_RoutesUnresolvedDeclaredHandoffRequestAsync()
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        TestReplayAgent agent = new(
            [new ChatMessage(ChatRole.Assistant, [handoffRequest]) { MessageId = "handoff-message" }],
            TestAgentId,
            TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotCancelHandoffRequestForDifferentCompletedCallAsync()
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        FunctionResultContent unrelatedCompletion = new("different-call", "Completed");
        TestReplayAgent agent = new(
        [
            new ChatMessage(ChatRole.Assistant, [handoffRequest]) { MessageId = "handoff-message" },
            new ChatMessage(ChatRole.Tool, [unrelatedCompletion]) { MessageId = "unrelated-completion" },
        ], TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Theory]
    [InlineData("", true)]
    [InlineData("provider-tool-call", false)]
    public async Task Test_HandoffAgentExecutor_DoesNotRouteIneligibleHandoffNamedContentAsync(string callId, bool assistantRole)
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent ineligibleRequest = new(callId, $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        TestReplayAgent agent = new(
            [new ChatMessage(assistantRole ? ChatRole.Assistant : ChatRole.Tool, [ineligibleRequest]) { MessageId = "ineligible-message" }],
            TestAgentId,
            TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.False(testContext.QueuedMessages.ContainsKey(executor.Id));
        FunctionCallContent externalRequest = Assert.IsType<FunctionCallContent>(Assert.Single(testContext.ExternalRequests).Data.As<FunctionCallContent>());
        Assert.Same(ineligibleRequest, externalRequest);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_RoutesHandoffRequestWithoutAgentProvenanceAsync()
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent nestedRequest = new("nested-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        AgentIdOverrideReplayAgent agent = new(nestedRequest, null, TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
        Assert.Empty(testContext.ExternalRequests);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotRouteHandoffRequestFromDifferentAgentAsync()
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        FunctionCallContent nestedRequest = new("nested-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        AgentIdOverrideReplayAgent agent = new(nestedRequest, "different-agent", TestAgentId, TestAgentName);

        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        // Act
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        // Assert
        Assert.False(testContext.QueuedMessages.ContainsKey(executor.Id));
        FunctionCallContent externalRequest = Assert.IsType<FunctionCallContent>(Assert.Single(testContext.ExternalRequests).Data.As<FunctionCallContent>());
        Assert.Same(nestedRequest, externalRequest);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_InheritsRoleWithinMessageAsync()
    {
        // Arrange
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, "message", "response", new TextContent("Thinking")),
            CreateUpdate(null, TestAgentId, "message", "response", handoffRequest),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, TestEchoAgent targetAgent) =
            await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_InheritsForeignAgentWithinMessageAsync()
    {
        // Arrange
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, "different-agent", "message", "response", new TextContent("Thinking")),
            CreateUpdate(null, null, "message", "response", handoffRequest),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, _) = await RunHandoffAgentAsync(agent);

        // Assert
        Assert.False(testContext.QueuedMessages.ContainsKey(executor.Id));
        FunctionCallContent externalRequest = Assert.IsType<FunctionCallContent>(Assert.Single(testContext.ExternalRequests).Data.As<FunctionCallContent>());
        Assert.Same(handoffRequest, externalRequest);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotInheritForeignAgentAcrossMessagesAsync()
    {
        // Arrange
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, "different-agent", "foreign-message", "response", new TextContent("Nested response")),
            CreateUpdate(ChatRole.Assistant, null, "direct-message", "response", handoffRequest),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, TestEchoAgent targetAgent) =
            await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Theory]
    [InlineData("different-message", "response")]
    [InlineData("message", "different-response")]
    public async Task Test_HandoffAgentExecutor_DoesNotInheritRoleAcrossMessageOrResponseAsync(string messageId, string responseId)
    {
        // Arrange
        FunctionCallContent handoffRequest = new("handoff-call", $"{HandoffWorkflowBuilder.FunctionPrefix}1");
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, "message", "response", new TextContent("Thinking")),
            CreateUpdate(null, TestAgentId, messageId, responseId, handoffRequest),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, _) = await RunHandoffAgentAsync(agent);

        // Assert
        Assert.False(testContext.QueuedMessages.ContainsKey(executor.Id));
        FunctionCallContent externalRequest = Assert.IsType<FunctionCallContent>(Assert.Single(testContext.ExternalRequests).Data.As<FunctionCallContent>());
        Assert.Same(handoffRequest, externalRequest);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotCancelHandoffForForeignProducerAsync()
    {
        // Arrange
        const string CallId = "handoff-call";
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, "request-message", "response", new FunctionCallContent(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")),
            CreateUpdate(ChatRole.Tool, "different-agent", "result-message", "response", new FunctionResultContent(CallId, "Completed")),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, TestEchoAgent targetAgent) =
            await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_DoesNotCancelHandoffForDifferentResponseAsync()
    {
        // Arrange
        const string CallId = "handoff-call";
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, "request-message", "request-response", new FunctionCallContent(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")),
            CreateUpdate(ChatRole.Tool, TestAgentId, "result-message", "different-response", new FunctionResultContent(CallId, "Completed")),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, TestEchoAgent targetAgent) =
            await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
    }

    [Theory]
    [InlineData("response")]
    [InlineData(null)]
    public async Task Test_HandoffAgentExecutor_CancelsHandoffForSameProducerAndResponseAsync(string? responseId)
    {
        // Arrange
        const string CallId = "handoff-call";
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, responseId is null ? null : "request-message", responseId, new FunctionCallContent(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")),
            CreateUpdate(ChatRole.Tool, TestAgentId, null, null, new FunctionResultContent(CallId, "Completed")),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, _) = await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Null(sentState.RequestedHandoffTargetAgentId);
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_CancelsAnonymousHandoffAfterMetadataOnlyDeltaAsync()
    {
        // Arrange
        const string CallId = "handoff-call";
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Assistant, TestAgentId, null, null, new TextContent("Thinking")),
            CreateUpdate(null, null, null, null, new FunctionCallContent(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")),
            CreateUpdate(ChatRole.Tool, null, null, null, new FunctionResultContent(CallId, "Completed")),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, _) = await RunHandoffAgentAsync(agent);

        // Assert
        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Null(sentState.RequestedHandoffTargetAgentId);
    }

    [Theory]
    [InlineData("different-agent", "response", true)]
    [InlineData(TestAgentId, "different-response", true)]
    [InlineData(TestAgentId, "response", false)]
    public async Task Test_HandoffAgentExecutor_ScopesCompletionBeforeHandoffRequestAsync(
        string completionAgentId,
        string completionResponseId,
        bool expectedHandoff)
    {
        // Arrange
        const string CallId = "handoff-call";
        StreamingUpdatesReplayAgent agent = new(
        [
            CreateUpdate(ChatRole.Tool, completionAgentId, "result-message", completionResponseId, new FunctionResultContent(CallId, "Completed")),
            CreateUpdate(ChatRole.Assistant, TestAgentId, "request-message", "response", new FunctionCallContent(CallId, $"{HandoffWorkflowBuilder.FunctionPrefix}1")),
        ], TestAgentId, TestAgentName);

        // Act
        (TestRunContext testContext, HandoffAgentExecutor executor, TestEchoAgent targetAgent) =
            await RunHandoffAgentAsync(agent);

        // Assert
        if (expectedHandoff)
        {
            HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
            Assert.Equal(targetAgent.Id, sentState.RequestedHandoffTargetAgentId);
        }
        else
        {
            Assert.False(testContext.QueuedMessages.ContainsKey(executor.Id));
        }
    }

    [Fact]
    public async Task Test_HandoffAgentExecutor_CancellationDoesNotRetainHandoffCandidateAsync()
    {
        // Arrange
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        CancellableHandoffReplayAgent agent = new(TestAgentId, TestAgentName);
        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);
        using CancellationTokenSource cancellationSource = new();

        // Act
        Task cancelledTurn = executor
            .HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id), cancellationSource.Token)
            .AsTask();
        await agent.FirstRequestObserved.Task;
        cancellationSource.Cancel();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => cancelledTurn);
        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        HandoffState sentState = Assert.IsType<HandoffState>(Assert.Single(testContext.QueuedMessages[executor.Id]).Message);
        Assert.Null(sentState.RequestedHandoffTargetAgentId);
    }

    private static AgentResponseUpdate CreateUpdate(
        ChatRole? role,
        string? agentId,
        string? messageId,
        string? responseId,
        AIContent content) =>
        new()
        {
            Role = role,
            AgentId = agentId,
            MessageId = messageId,
            ResponseId = responseId,
            Contents = [content],
        };

    private static async Task<(TestRunContext Context, HandoffAgentExecutor Executor, TestEchoAgent TargetAgent)> RunHandoffAgentAsync(AIAgent agent)
    {
        TestEchoAgent targetAgent = new("target-agent", "Target Agent");
        HandoffAgentExecutorOptions options = new("",
                                                  emitAgentResponseEvents: false,
                                                  emitAgentResponseUpdateEvents: false,
                                                  HandoffToolCallFilteringBehavior.None);
        HandoffAgentExecutor executor = new(agent, [new HandoffTarget(targetAgent)], options);
        TestRunContext testContext = await PrepareHandoffSharedStateAsync();
        testContext.ConfigureExecutor(executor);

        await executor.HandleAsync(new HandoffState(new(false), null, null), testContext.BindWorkflowContext(executor.Id));

        return (testContext, executor, targetAgent);
    }
}

internal sealed record Challenge(string Value);
internal sealed record Response(string Value);

[SendsMessage(typeof(Challenge))]
internal sealed partial class SendsRequestExecutor(string? id = null) : ChatProtocolExecutor(id ?? nameof(SendsRequestExecutor), s_chatOptions)
{
    internal const string ChallengeString = "{C7A762AE-7DAA-4D9C-A647-E64E6DBC35AE}";
    private static string ResponseKey { get; } = new(ChallengeString.Reverse().ToArray());

    private static readonly ChatProtocolExecutorOptions s_chatOptions = new()
    {
        AutoSendTurnToken = false
    };

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => context.SendMessageAsync(new Challenge(ChallengeString), cancellationToken);

    [MessageHandler]
    public async ValueTask HandleChallengeResponseAsync(Response response, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (response.Value != ResponseKey)
        {
            throw new InvalidOperationException($"Incorrect response received. Expected '{ResponseKey}' but got '{response.Value}'");
        }

        await context.SendMessageAsync(new ChatMessage(ChatRole.Assistant, "Correct response."), cancellationToken)
                     .ConfigureAwait(false);

        await context.SendMessageAsync(new TurnToken(false), cancellationToken).ConfigureAwait(false);
    }
}

internal sealed class OptionValidatingChatClient(string baseInstructions, string handoffInstructions, AITool baseTool) : IChatClient
{
    public void Dispose()
    {
    }

    private void CheckOptions(ChatOptions? options)
    {
        Assert.NotNull(options);

        Assert.False(string.IsNullOrEmpty(options.Instructions));
        Assert.Contains(baseInstructions, options.Instructions);
        Assert.Contains(handoffInstructions, options.Instructions);

        Assert.NotNull(options.Tools);
        Assert.NotEmpty(options.Tools);
        Assert.Contains(options.Tools, tool => tool.Name == baseTool.Name);
        Assert.Contains(options.Tools, tool => tool.Name.StartsWith(HandoffWorkflowBuilder.FunctionPrefix, StringComparison.Ordinal));
    }

    private List<ChatMessage> ResponseMessages =>
        [
            new ChatMessage(ChatRole.Assistant, "Ok")
                {
                    MessageId = Guid.NewGuid().ToString(),
                    AuthorName = nameof(OptionValidatingChatClient)
                }
        ];

    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        this.CheckOptions(options);

        ChatResponse response = new(this.ResponseMessages)
        {
            ResponseId = Guid.NewGuid().ToString("N"),
            CreatedAt = DateTimeOffset.Now
        };

        return Task.FromResult(response);
    }

    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        if (serviceType == typeof(OptionValidatingChatClient))
        {
            return this;
        }

        return null;
    }

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.CheckOptions(options);

        string responseId = Guid.NewGuid().ToString("N");
        foreach (ChatMessage message in this.ResponseMessages)
        {
            yield return new(message.Role, message.Contents)
            {
                ResponseId = responseId,
                MessageId = message.MessageId,
                CreatedAt = DateTimeOffset.Now
            };
        }
    }
}
