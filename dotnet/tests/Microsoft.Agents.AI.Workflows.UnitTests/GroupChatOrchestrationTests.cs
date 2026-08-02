// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Orchestration-level tests for <see cref="AgentWorkflowBuilder.CreateGroupChatBuilderWith"/> covering
/// <see cref="FunctionCallContent"/> and <see cref="ToolApprovalRequestContent"/> behavior across
/// real <see cref="ChatClientAgent"/> participants. These tests parallel the equivalents in
/// <see cref="HandoffOrchestrationTests"/> to ensure that the broadcast-based group chat host
/// (each participant maintains its own per-agent session via <see cref="Specialized.AIAgentHostExecutor"/>;
/// only the speaker receives a <see cref="TurnToken"/>; messages are broadcast to every other
/// participant) preserves the same HITL semantics as the handoff path.
/// </summary>
public class GroupChatOrchestrationTests
{
    /// <summary>
    /// End-to-end tool-approval checkpoint/resume scenario through a <see cref="RoundRobinGroupChatManager"/>
    /// with a single participant. Mirrors the maximal repro added in PR #5952 (Track A2 in
    /// <c>docs/working/issue-5350-root-cause-validation-plan.md</c>): a <see cref="ChatClientAgent"/>
    /// over a mock chat client emits a <see cref="FunctionCallContent"/> for an
    /// <see cref="ApprovalRequiredAIFunction"/>, the runtime surfaces a
    /// <see cref="ToolApprovalRequestContent"/> as an external <see cref="RequestInfoEvent"/>, the test
    /// checkpoints while the request is pending, resumes from a fresh handle, asserts that the
    /// resumed <c>TARC.ToolCall</c> is still a <see cref="FunctionCallContent"/>, sends an
    /// approval response, and verifies that the wrapped <see cref="AIFunction"/> is invoked
    /// exactly once and the workflow completes without errors.
    /// </summary>
    [Fact]
    public async Task GroupChat_ToolApproval_JsonCheckpointResume_PreservesFunctionCallContentAndInvokesToolAsync()
    {
        ApprovalHarness harness = new();
        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 4 })
            .AddParticipants(harness.Agent)
            .Build();

        await RunCheckpointedApprovalRoundTripAsync(
            workflow,
            harness,
            CheckpointManager.CreateJson(new InMemoryJsonStore()),
            scenarioName: "GroupChat (round-robin, single participant)");
    }

    /// <summary>
    /// Round-robin group chat with two participants. The first participant exposes an
    /// <see cref="ApprovalRequiredAIFunction"/> and emits a <see cref="FunctionCallContent"/> for it on
    /// its first turn. The test denies the approval and asserts that the conversation continues:
    /// the first agent runs once more (the FICC denial branch produces a final assistant message),
    /// then the host broadcasts that message and selects the second agent, which produces its own
    /// reply. This mirrors <c>Handoffs_TwoTransfers_SecondAgentUserApproval_ResponseServedByThirdAgentAsync</c>
    /// but on the group-chat path.
    /// </summary>
    [Fact]
    public async Task GroupChat_ToolApproval_DeniedResponse_ConversationContinuesAsync()
    {
        int approvalToolCallCount = 0;

        const string ApprovalCallId = "approve_call_1";
        const string ApprovalToolName = "DoSomethingPrivileged";

        AIFunction approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(
            () =>
            {
                Interlocked.Increment(ref approvalToolCallCount);
                return "tool result";
            },
            name: ApprovalToolName,
            description: "Performs a privileged action"));

        int agent1CallCount = 0;
        var agent1 = new ChatClientAgent(
            new MockChatClient((messages, options) =>
            {
                int call = Interlocked.Increment(ref agent1CallCount);
                return call switch
                {
                    1 => new ChatResponse(new ChatMessage(ChatRole.Assistant,
                        [new FunctionCallContent(ApprovalCallId, ApprovalToolName)])),
                    _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "agent1 final response")),
                };
            }),
            instructions: "You are agent1.",
            name: "agent1",
            tools: [approvalTool]);

        int agent2CallCount = 0;
        var agent2 = new ChatClientAgent(
            new MockChatClient((messages, options) =>
            {
                Interlocked.Increment(ref agent2CallCount);
                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "agent2 reply"));
            }),
            instructions: "You are agent2.",
            name: "agent2");

        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(agent1, agent2)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = InProcessExecution.OffThread.WithCheckpointing(checkpointManager);

        ExternalRequest? pendingRequest = null;
        CheckpointInfo? lastCheckpoint = null;
        List<WorkflowEvent> firstRunEvents = [];

        await using (StreamingRun firstRun = await env.RunStreamingAsync(workflow, new List<ChatMessage> { new(ChatRole.User, "hello") }))
        {
            (await firstRun.TrySendMessageAsync(new TurnToken(emitEvents: false)))
                .Should().BeTrue();

            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                firstRunEvents.Add(evt);
                if (evt is RequestInfoEvent requestInfo)
                {
                    pendingRequest ??= requestInfo.Request;
                }
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    lastCheckpoint = cp;
                }
            }
        }

        pendingRequest.Should().NotBeNull("agent1 should have surfaced an approval request for the privileged tool");
        firstRunEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty();
        firstRunEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty();
        approvalToolCallCount.Should().Be(0, "the tool must not be invoked before approval is granted");

        ToolApprovalRequestContent approvalRequest =
            pendingRequest!.Data.As<ToolApprovalRequestContent>().Should().NotBeNull()
                                                                 .And.Subject.As<ToolApprovalRequestContent>();
        approvalRequest.ToolCall.Should().BeOfType<FunctionCallContent>();
        ((FunctionCallContent)approvalRequest.ToolCall).Name.Should().Be(ApprovalToolName);

        // Deny the request and continue the conversation.
        ExternalResponse denial = pendingRequest.CreateResponse(approvalRequest.CreateResponse(approved: false, reason: "Denied"));

        List<WorkflowEvent> secondRunEvents = [];
        List<ChatMessage>? finalOutput = null;
        await using (StreamingRun resumed = await env.ResumeStreamingAsync(workflow, lastCheckpoint!))
        {
            await resumed.SendResponseAsync(denial);

            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                secondRunEvents.Add(evt);
                if (evt is WorkflowOutputEvent outputEvt)
                {
                    finalOutput = outputEvt.As<List<ChatMessage>>();
                }
            }
        }

        secondRunEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "denying the approval should not surface any workflow errors");
        secondRunEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty(
            "denying the approval should not raise executor failures (regression guard for the GroupChat duplicate-key bug pinned in PR #5952's A2 test before the broadcast refactor)");

        approvalToolCallCount.Should().Be(0, "the tool must not be invoked after denial");
        agent1CallCount.Should().BeGreaterThanOrEqualTo(2, "agent1 should be re-invoked by FICC after the denial to produce a final assistant message");
        agent2CallCount.Should().Be(1, "agent2 should be the next round-robin speaker and produce its own reply");

        finalOutput.Should().NotBeNull();
        finalOutput!.Should().Contain(m => m.AuthorName == "agent1");
        finalOutput.Should().Contain(m => m.AuthorName == "agent2" && m.Text == "agent2 reply");
    }

    /// <summary>
    /// Round-robin group chat with two participants. The first participant declares a
    /// non-invokable function via <c>AIFunctionFactory.CreateDeclaration</c>,
    /// causing the function call to be surfaced as an external <see cref="FunctionCallContent"/>
    /// (<see cref="RequestInfoEvent"/>). The test responds with a <see cref="FunctionResultContent"/>
    /// and asserts that the conversation continues: the first agent's second invocation produces a
    /// final assistant message, then the group chat advances to the second agent which produces
    /// its own reply. This mirrors <c>Handoffs_TwoTransfers_SecondAgentToolCall_ResponseServedByThirdAgentAsync</c>
    /// but on the group-chat path.
    /// </summary>
    [Fact]
    public async Task GroupChat_FunctionCall_ExternallyResolved_ConversationContinuesAsync()
    {
        const string FunctionCallId = "fcc_call_1";
        const string FunctionName = "FetchExternalData";

        JsonElement schema = AIFunctionFactory.Create(() => true).JsonSchema;
        AIFunctionDeclaration declaration = AIFunctionFactory.CreateDeclaration(FunctionName, "Fetches external data", schema);

        int agent1CallCount = 0;
        var agent1 = new ChatClientAgent(
            new MockChatClient((messages, options) =>
            {
                int call = Interlocked.Increment(ref agent1CallCount);
                return call switch
                {
                    1 => new ChatResponse(new ChatMessage(ChatRole.Assistant,
                        [new FunctionCallContent(FunctionCallId, FunctionName)])),
                    _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, "agent1 final response")),
                };
            }),
            instructions: "You are agent1.",
            name: "agent1",
            tools: [declaration]);

        int agent2CallCount = 0;
        var agent2 = new ChatClientAgent(
            new MockChatClient((messages, options) =>
            {
                Interlocked.Increment(ref agent2CallCount);
                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "agent2 reply"));
            }),
            instructions: "You are agent2.",
            name: "agent2");

        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(agent1, agent2)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateInMemory();
        InProcessExecutionEnvironment env = InProcessExecution.OffThread.WithCheckpointing(checkpointManager);

        ExternalRequest? pendingRequest = null;
        CheckpointInfo? lastCheckpoint = null;

        await using (StreamingRun firstRun = await env.RunStreamingAsync(workflow, new List<ChatMessage> { new(ChatRole.User, "hello") }))
        {
            (await firstRun.TrySendMessageAsync(new TurnToken(emitEvents: false)))
                .Should().BeTrue();

            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    pendingRequest ??= requestInfo.Request;
                }
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    lastCheckpoint = cp;
                }
            }
        }

        pendingRequest.Should().NotBeNull("agent1 should have surfaced a FunctionCallContent for the declaration-only tool");

        FunctionCallContent functionCall =
            pendingRequest!.Data.As<FunctionCallContent>().Should().NotBeNull()
                                                          .And.Subject.As<FunctionCallContent>();
        functionCall.Name.Should().Be(FunctionName);
        functionCall.CallId.Should().EndWith(FunctionCallId,
            "the workflow rewrites the CallId with an executor-scoped prefix, but should preserve the original tail");

        // Respond with a function result and let the conversation continue.
        ExternalResponse response = pendingRequest.CreateResponse(new FunctionResultContent(functionCall.CallId, "external-data-payload"));

        List<WorkflowEvent> resumeEvents = [];
        List<ChatMessage>? finalOutput = null;
        await using (StreamingRun resumed = await env.ResumeStreamingAsync(workflow, lastCheckpoint!))
        {
            await resumed.SendResponseAsync(response);

            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                resumeEvents.Add(evt);
                if (evt is WorkflowOutputEvent outputEvt)
                {
                    finalOutput = outputEvt.As<List<ChatMessage>>();
                }
            }
        }

        resumeEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty();
        resumeEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty();

        agent1CallCount.Should().BeGreaterThanOrEqualTo(2, "agent1 should be re-invoked once the externally-resolved function result is delivered");
        agent2CallCount.Should().Be(1, "agent2 should be the next round-robin speaker after agent1 finishes");

        finalOutput.Should().NotBeNull();
        finalOutput!.Should().Contain(m => m.AuthorName == "agent1");
        finalOutput.Should().Contain(m => m.AuthorName == "agent2" && m.Text == "agent2 reply");
    }

    /// <summary>
    /// Shared end-to-end driver for the approval checkpoint/resume scenario; modelled on the
    /// <c>RunReproAsync</c> helper from PR #5952. Runs the workflow until an approval request is
    /// pending, captures the latest checkpoint, disposes the run, resumes from a fresh handle,
    /// asserts the resumed payload still carries a <see cref="FunctionCallContent"/>, sends an
    /// approval response, and asserts the wrapped tool is invoked exactly once and the workflow
    /// finishes without errors.
    /// </summary>
    private static async Task RunCheckpointedApprovalRoundTripAsync(
        Workflow workflow,
        ApprovalHarness harness,
        CheckpointManager checkpointManager,
        string scenarioName)
    {
        InProcessExecutionEnvironment env = InProcessExecution.OffThread;
        List<ChatMessage> inputMessages = [new(ChatRole.User, "What's the weather in Amsterdam?")];

        ExternalRequest? firstRunRequest = null;
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, inputMessages))
        {
            (await firstRun.TrySendMessageAsync(new TurnToken(emitEvents: false)))
                .Should().BeTrue($"[{scenarioName}] the workflow should accept a TurnToken");

            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    firstRunRequest ??= requestInfo.Request;
                }
                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }
        }

        firstRunRequest.Should().NotBeNull(
            $"[{scenarioName}] the ChatClientAgent + FICC pipeline should surface the approval request as a workflow RequestInfoEvent");
        checkpoint.Should().NotBeNull(
            $"[{scenarioName}] a checkpoint should have been produced while the approval request was pending");
        harness.ChatCallCount.Should().Be(1, $"[{scenarioName}] the mock chat client should have been called exactly once before approval was requested");
        harness.InvocationCount.Should().Be(0, $"[{scenarioName}] the underlying tool must NOT have been invoked before approval was granted");

        ToolApprovalRequestContent? preCheckpoint = firstRunRequest!.Data.As<ToolApprovalRequestContent>();
        preCheckpoint.Should().NotBeNull($"[{scenarioName}] the pending external request should carry a ToolApprovalRequestContent payload");
        preCheckpoint!.ToolCall.Should().BeOfType<FunctionCallContent>(
            $"[{scenarioName}] the pre-checkpoint pending request payload must already be a FunctionCallContent");

        // Resume on a fresh handle and capture the re-emitted approval request.
        ExternalRequest? resumedRequest = null;
        List<WorkflowEvent> postResumeEvents = [];

        await using (StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                     .ResumeStreamingAsync(workflow, checkpoint!))
        {
            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    resumedRequest ??= requestInfo.Request;
                }
            }

            resumedRequest.Should().NotBeNull($"[{scenarioName}] the resumed workflow should re-emit the pending approval RequestInfoEvent");

            ToolApprovalRequestContent? postResume = resumedRequest!.Data.As<ToolApprovalRequestContent>();
            postResume.Should().NotBeNull(
                $"[{scenarioName}] ExternalRequest.Data.As<ToolApprovalRequestContent>() should materialize the payload after JSON-checkpoint resume");
            postResume!.ToolCall.Should().NotBeNull($"[{scenarioName}] the resumed TARC must carry its ToolCall");
            postResume.ToolCall.Should().BeOfType<FunctionCallContent>(
                $"[{scenarioName}] after CheckpointManager.CreateJson round-trip via ResumeStreamingAsync, " +
                "ToolApprovalRequestContent.ToolCall must still be a FunctionCallContent so that " +
                "FunctionInvokingChatClient's pattern match (`tarc.ToolCall is FunctionCallContent`) continues to fire.");

            ToolApprovalResponseContent approvalResponse = postResume.CreateResponse(approved: true);
            await resumed.SendResponseAsync(resumedRequest.CreateResponse(approvalResponse));

            using CancellationTokenSource cts2 = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts2.Token))
            {
                postResumeEvents.Add(evt);
            }
        }

        harness.InvocationCount.Should().Be(1,
            $"[{scenarioName}] approving the request should cause FunctionInvokingChatClient to invoke the wrapped AIFunction exactly once");
        postResumeEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            $"[{scenarioName}] no workflow errors should be raised when responding to the resumed approval request");
        postResumeEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty(
            $"[{scenarioName}] no executor failures should be raised when responding to the resumed approval request " +
            "(regression guard: pre-broadcast-refactor this test was the `Track A2` repro in PR #5952 which surfaced a " +
            "duplicate-key ArgumentException out of FunctionInvokingChatClient.ExtractAndRemoveApprovalRequestsAndResponses).");
    }

    /// <summary>
    /// Bundles a <see cref="ChatClientAgent"/> with a counting <see cref="ApprovalRequiredAIFunction"/>
    /// tool and a <see cref="MockChatClient"/> that emits a function call on the first chat turn
    /// and a final assistant text on subsequent turns (after FICC has processed the approval
    /// and appended a <see cref="FunctionResultContent"/>).
    /// </summary>
    private sealed class ApprovalHarness
    {
        public const string ToolName = "GetWeather";
        public const string ToolResultText = "Sunny, 22°C";
        public const string ToolCallId = "call-1";
        public const string FinalAssistantText = "The weather in Amsterdam is sunny and 22°C.";

        private int _invocationCount;
        private int _chatCallIndex;

        public int InvocationCount => Volatile.Read(ref this._invocationCount);
        public int ChatCallCount => Volatile.Read(ref this._chatCallIndex);

        public ChatClientAgent Agent { get; }

        public ApprovalHarness()
        {
            AIFunction underlyingTool = AIFunctionFactory.Create(
                ([Description("City to look up")] string city) =>
                {
                    Interlocked.Increment(ref this._invocationCount);
                    return ToolResultText;
                },
                name: ToolName,
                description: "Gets the weather for the given city");

            ApprovalRequiredAIFunction approvalTool = new(underlyingTool);

            MockChatClient mockChatClient = new((messages, options) =>
            {
                int index = Interlocked.Increment(ref this._chatCallIndex) - 1;
                return index switch
                {
                    0 => new ChatResponse(new ChatMessage(ChatRole.Assistant,
                        [new FunctionCallContent(
                            callId: ToolCallId,
                            name: ToolName,
                            arguments: new Dictionary<string, object?> { ["city"] = "Amsterdam" })])),
                    _ => new ChatResponse(new ChatMessage(ChatRole.Assistant, FinalAssistantText)),
                };
            });

            this.Agent = new ChatClientAgent(
                mockChatClient,
                instructions: "You are a weather agent.",
                name: "WeatherAgent",
                tools: [approvalTool]);
        }
    }

    /// <summary>
    /// Minimal <see cref="IChatClient"/> stub for orchestration tests; delegates each call to a
    /// caller-supplied factory.
    /// </summary>
    private sealed class MockChatClient(Func<IEnumerable<ChatMessage>, ChatOptions?, ChatResponse> responseFactory) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(responseFactory(messages, options));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages,
            ChatOptions? options = null,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            ChatResponse response = await this.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
            foreach (ChatResponseUpdate update in response.ToChatResponseUpdates())
            {
                yield return update;
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) => null;
        public void Dispose() { }
    }
}
