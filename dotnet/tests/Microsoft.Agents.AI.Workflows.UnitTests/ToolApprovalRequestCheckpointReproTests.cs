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
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Repro tests for issue #5350: <c>ToolApprovalRequestContent.ToolCall</c> reportedly loses its
/// concrete <see cref="FunctionCallContent"/> type after being persisted via a
/// <c>JsonCheckpointStore</c>-backed <c>CheckpointManager</c> and restored on resume.
///
/// These tests bypass the OP's SQL-backed store and HITL agent setup and directly exercise
/// the same JSON pipeline used by the checkpoint path (<see cref="JsonMarshaller"/> ->
/// <see cref="PortableValueConverter"/> -> <see cref="WorkflowsJsonUtilities"/>.DefaultOptions,
/// which chains through AgentAbstractionsJsonUtilities -> AIJsonUtilities), at progressively
/// more end-to-end layers up to a full <c>CheckpointManager.CreateJson(...)</c> +
/// <c>RunStreamingAsync</c> / <c>ResumeStreamingAsync</c> cycle.
///
/// At the time of writing all of these tests <b>pass</b>, which provides counter-evidence
/// against the root-cause hypothesis stated in the issue body (missing polymorphism
/// metadata / serializer-options chain). See
/// <c>docs/working/issue-5350-root-cause-validation-plan.md</c> for the full investigation
/// plan that builds on this baseline.
/// </summary>
public class ToolApprovalRequestCheckpointReproTests
{
    private const string RequestId = "req-1";
    private const string CallId = "call-1";
    private const string FunctionName = "DoTheThing";

    private static FunctionCallContent MakeFunctionCall() => new(
        callId: CallId,
        name: FunctionName,
        arguments: new Dictionary<string, object?> { ["x"] = 42 });

    private static ToolApprovalRequestContent MakeApprovalRequest()
        => new(RequestId, MakeFunctionCall());

    /// <summary>
    /// Direct round-trip of a <see cref="ToolApprovalRequestContent"/> through the same
    /// <see cref="JsonMarshaller"/> used by <c>CheckpointManager.CreateJson(...)</c>.
    ///
    /// Per the issue, after deserialization the <c>ToolCall</c> property (declared as the
    /// abstract base <c>ToolCallContent</c>) is expected to remain a
    /// <see cref="FunctionCallContent"/>. If polymorphism is preserved, this test passes;
    /// if the discriminator is dropped on the wire or on read, <c>ToolCall</c> comes back
    /// as something other than <see cref="FunctionCallContent"/> and FICC's pattern match
    /// (<c>tarc.ToolCall is FunctionCallContent { InformationalOnly: false }</c>) silently
    /// skips the approval pair.
    /// </summary>
    [Fact]
    public void Repro_5350_ToolApprovalRequestContent_DirectJsonMarshallerRoundtrip_PreservesFunctionCallContent()
    {
        ToolApprovalRequestContent original = MakeApprovalRequest();

        ToolApprovalRequestContent roundTripped = JsonSerializationTests.RunJsonRoundtrip(original);

        roundTripped.Should().NotBeNull();
        roundTripped.RequestId.Should().Be(RequestId);
        roundTripped.ToolCall.Should().NotBeNull();

        // This is the assertion that, per issue #5350, fails on resume.
        roundTripped.ToolCall.Should().BeOfType<FunctionCallContent>(
            "ToolApprovalRequestContent.ToolCall must round-trip as its concrete FunctionCallContent type, " +
            "otherwise FunctionInvokingChatClient.ExtractAndRemoveApprovalRequestsAndResponses will silently " +
            "skip the approval pair after a checkpoint resume (issue #5350).");

        FunctionCallContent? fcc = roundTripped.ToolCall as FunctionCallContent;
        fcc!.CallId.Should().Be(CallId);
        fcc.Name.Should().Be(FunctionName);
    }

    /// <summary>
    /// Same round-trip as above, but wrapped in a <see cref="PortableValue"/>. This more closely
    /// mirrors how the workflow runtime stores externally-visible request payloads in a checkpoint
    /// (<see cref="PortableMessageEnvelope"/> / <see cref="PortableValue"/>). The
    /// <see cref="PortableValueConverter"/> serializes the inner value with
    /// <c>marshaller.Marshal(value.Value, value.Value.GetType())</c>, so on the write side the
    /// runtime type is used (which should include the discriminator), and on the read side the
    /// inner value is materialized as a <see cref="JsonElement"/> then re-deserialized as the
    /// declared type via <see cref="PortableValue.As{T}"/>.
    /// </summary>
    [Fact]
    public void Repro_5350_ToolApprovalRequestContent_WrappedInPortableValue_PreservesFunctionCallContent()
    {
        PortableValue original = new(MakeApprovalRequest());

        PortableValue result = JsonSerializationTests.RunJsonRoundtrip(original);

        ToolApprovalRequestContent? extracted = result.As<ToolApprovalRequestContent>();
        extracted.Should().NotBeNull();
        extracted!.RequestId.Should().Be(RequestId);
        extracted.ToolCall.Should().NotBeNull();
        extracted.ToolCall.Should().BeOfType<FunctionCallContent>(
            "PortableValue-wrapped ToolApprovalRequestContent must preserve the concrete " +
            "FunctionCallContent on the ToolCall property after checkpoint round-trip (issue #5350).");
    }

    /// <summary>
    /// Round-trip the <see cref="ToolApprovalRequestContent"/> as the payload of an
    /// <see cref="ExternalRequest"/>, which is the actual on-the-wire shape for HITL approval
    /// requests flowing out of a workflow. This is the closest serializer-only proxy for what
    /// happens when the issue reporter calls
    /// <c>request.TryGetDataAs&lt;ToolApprovalRequestContent&gt;()</c> after
    /// <c>InProcessExecution.ResumeStreamingAsync(...)</c>.
    /// </summary>
    [Fact]
    public void Repro_5350_ToolApprovalRequestContent_AsExternalRequestData_PreservesFunctionCallContent()
    {
        RequestPort<ToolApprovalRequestContent, ToolApprovalResponseContent> port
            = RequestPort.Create<ToolApprovalRequestContent, ToolApprovalResponseContent>("Approval");

        ExternalRequest original = ExternalRequest.Create(port, MakeApprovalRequest(), RequestId);

        ExternalRequest result = JsonSerializationTests.RunJsonRoundtrip(original);

        ToolApprovalRequestContent? extracted = result.Data.As<ToolApprovalRequestContent>();
        extracted.Should().NotBeNull();
        extracted!.ToolCall.Should().NotBeNull();
        extracted.ToolCall.Should().BeOfType<FunctionCallContent>(
            "ExternalRequest.Data restored from a JSON checkpoint must preserve the concrete " +
            "FunctionCallContent on ToolApprovalRequestContent.ToolCall (issue #5350).");
    }

    /// <summary>
    /// Stability check: run the direct round-trip many times in a row to demonstrate that
    /// the failure mode (if present) is deterministic and not a flaky/JIT-order artifact.
    /// </summary>
    [Fact]
    public void Repro_5350_DirectJsonMarshallerRoundtrip_IsDeterministic()
    {
        for (int i = 0; i < 25; i++)
        {
            ToolApprovalRequestContent original = MakeApprovalRequest();
            ToolApprovalRequestContent roundTripped = JsonSerializationTests.RunJsonRoundtrip(original);

            roundTripped.ToolCall.Should().BeOfType<FunctionCallContent>(
                $"iteration {i}: ToolCall must consistently round-trip as FunctionCallContent");
        }
    }

    /// <summary>
    /// End-to-end checkpoint -> resume repro using the actual <c>CheckpointManager.CreateJson(...)</c>
    /// path that the issue reporter uses. A trivial workflow whose entry point is a
    /// <c>RequestPort&lt;ToolApprovalRequestContent, ToolApprovalResponseContent&gt;</c> emits a
    /// pending external request containing a <see cref="FunctionCallContent"/>. We then:
    ///   1. checkpoint the run while the request is pending,
    ///   2. resume from the checkpoint via a fresh <c>InProcessExecution</c>,
    ///   3. read the re-emitted <see cref="RequestInfoEvent"/>, and
    ///   4. assert that <c>request.Data.As&lt;ToolApprovalRequestContent&gt;().ToolCall</c> is
    ///      still a <see cref="FunctionCallContent"/>.
    ///
    /// This is the closest serializer-and-runtime repro for issue #5350 that does not require a
    /// real <c>ChatClientAgent</c> + <c>ApprovalRequiredAIFunction</c>.
    /// </summary>
    [Fact]
    public async Task Repro_5350_EndToEnd_JsonCheckpointResume_PreservesFunctionCallContentAsync()
    {
        RequestPort<ToolApprovalRequestContent, ToolApprovalResponseContent> requestPort
            = RequestPort.Create<ToolApprovalRequestContent, ToolApprovalResponseContent>("ApprovalPort");
        ForwardMessageExecutor<ToolApprovalResponseContent> processor = new("Processor");

        Workflow workflow = new WorkflowBuilder(requestPort)
            .AddEdge(requestPort, processor)
            .Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateJson(new InMemoryJsonStore());
        InProcessExecutionEnvironment env = InProcessExecution.OffThread;

        ToolApprovalRequestContent input = MakeApprovalRequest();
        CheckpointInfo? checkpoint = null;
        ExternalRequest? originalPendingRequest = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, input))
        {
            await foreach (WorkflowEvent evt in firstRun.WatchStreamAsync(blockOnPendingRequest: false))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    originalPendingRequest ??= requestInfo.Request;
                }

                if (evt is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } cp)
                {
                    checkpoint = cp;
                }
            }
        }

        originalPendingRequest.Should().NotBeNull("the workflow should have emitted the approval request");
        checkpoint.Should().NotBeNull("a checkpoint should have been produced while the request was pending");

        // Sanity: the pre-checkpoint payload should be a FunctionCallContent.
        ToolApprovalRequestContent? preCheckpoint = originalPendingRequest!.Data.As<ToolApprovalRequestContent>();
        preCheckpoint.Should().NotBeNull();
        preCheckpoint!.ToolCall.Should().BeOfType<FunctionCallContent>(
            "the pre-checkpoint pending request payload must already be a FunctionCallContent");

        // Resume from the checkpoint and capture the re-emitted request.
        await using StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                    .ResumeStreamingAsync(workflow, checkpoint!);

        ExternalRequest? resumedPendingRequest = null;
        using CancellationTokenSource cts = new(TimeSpan.FromSeconds(10));
        await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
        {
            if (evt is RequestInfoEvent requestInfo)
            {
                resumedPendingRequest ??= requestInfo.Request;
            }
        }

        resumedPendingRequest.Should().NotBeNull("the resumed workflow should re-emit the pending request");

        ToolApprovalRequestContent? postResume = resumedPendingRequest!.Data.As<ToolApprovalRequestContent>();
        postResume.Should().NotBeNull(
            "ExternalRequest.Data.As<ToolApprovalRequestContent>() should materialize the payload after a JSON checkpoint resume");

        // The assertion that the issue reporter says fails.
        postResume!.ToolCall.Should().NotBeNull();
        postResume.ToolCall.Should().BeOfType<FunctionCallContent>(
            "after CheckpointManager.CreateJson round-trip via ResumeStreamingAsync, " +
            "ToolApprovalRequestContent.ToolCall must still be a FunctionCallContent so that " +
            "FunctionInvokingChatClient's pattern match (`tarc.ToolCall is FunctionCallContent`) continues to fire " +
            "(issue #5350).");
    }

    /// <summary>
    /// Captures the raw JSON produced for a <see cref="ToolApprovalRequestContent"/> by the
    /// checkpoint marshaller. This test always passes; it exists to make the on-the-wire shape
    /// visible in test output / debugger when investigating issue #5350 (e.g. to confirm the
    /// <c>"$type": "functionCall"</c> discriminator is or is not present for the inner
    /// <c>toolCall</c> property).
    /// </summary>
    [Fact]
    public void Repro_5350_CaptureWireFormat_ForInspection()
    {
        JsonMarshaller marshaller = new();

        JsonElement element = marshaller.Marshal(MakeApprovalRequest());
        string serialized = element.GetRawText();

        // Always-true assertion — purpose of this test is to expose the wire format.
        serialized.Should().NotBeNullOrEmpty();
        serialized.Should().Contain(CallId, "the call id should be present in the serialized form");
    }

    /// <summary>
    /// Maximal end-to-end repro for issue #5350 using the same shape as the OP's reported
    /// scenario (pattern "B" in the GroupChatToolApproval sample), but with a single
    /// <see cref="ChatClientAgent"/> bound directly into a <see cref="WorkflowBuilder"/>
    /// (no orchestration), and with a real <see cref="ApprovalRequiredAIFunction"/>-wrapped
    /// tool that the agent actually attempts to call. The test:
    /// <list type="number">
    /// <item>builds a <see cref="ChatClientAgent"/> over a <see cref="MockChatClient"/> that
    /// returns a <see cref="FunctionCallContent"/> on the first turn and a final assistant
    /// text on the second turn (so <see cref="FunctionInvokingChatClient"/> converts the FCC
    /// to a <see cref="ToolApprovalRequestContent"/> and surfaces it as a workflow
    /// <see cref="RequestInfoEvent"/>),</item>
    /// <item>persists checkpoints via the OP's exact path —
    /// <c>CheckpointManager.CreateJson(InMemoryJsonStore)</c> +
    /// <c>InProcessExecutionEnvironment.WithCheckpointing(...).RunStreamingAsync(...)</c> —
    /// so every checkpoint is round-tripped through the same <see cref="JsonMarshaller"/> +
    /// <see cref="PortableValueConverter"/> pipeline the OP's SQL-backed store uses,</item>
    /// <item>validates that the first-run <see cref="RequestInfoEvent.Request"/> carries a
    /// <see cref="ToolApprovalRequestContent"/> whose <c>ToolCall</c> is a
    /// <see cref="FunctionCallContent"/>,</item>
    /// <item>disposes the run and resumes from the last <see cref="SuperStepCompletedEvent"/>
    /// checkpoint via <see cref="InProcessExecutionEnvironment.ResumeStreamingAsync"/>,</item>
    /// <item>validates the re-emitted <see cref="RequestInfoEvent.Request"/> still carries a
    /// <see cref="ToolApprovalRequestContent"/> whose <c>ToolCall</c> is a
    /// <see cref="FunctionCallContent"/> — this is the assertion the OP claims fails,</item>
    /// <item>sends an approval response back into the resumed run and asserts the wrapped
    /// function is actually invoked (counter increments) and the workflow completes with a
    /// final assistant message.</item>
    /// </list>
    /// </summary>
    [Fact]
    public async Task Repro_5350_EndToEnd_ChatClientAgent_WithApprovalRequiredTool_JsonCheckpointResume_PreservesFunctionCallContentAndInvokesToolAsync()
    {
        // Arrange — counting tool wrapped for approval
        int invocationCount = 0;
        const string ToolName = "GetWeather";
        const string ToolResultText = "Sunny, 22°C";

        AIFunction underlyingTool = AIFunctionFactory.Create(
            ([Description("City to look up")] string city) =>
            {
                Interlocked.Increment(ref invocationCount);
                return ToolResultText;
            },
            name: ToolName,
            description: "Gets the weather for the given city");

        ApprovalRequiredAIFunction approvalTool = new(underlyingTool);

        // Arrange — mock chat client that turn-1 emits an FCC for the approval-required tool,
        // turn-2 (after FunctionInvokingChatClient processes the approval + invokes the tool +
        // appends a FunctionResultContent) emits a final assistant text.
        const string ToolCallId = "call-1";
        const string FinalAssistantText = "The weather in Amsterdam is sunny and 22°C.";
        int chatCallIndex = 0;
        List<List<ChatMessage>> capturedInputs = new();

        MockChatClient mockChatClient = new((messages, options) =>
        {
            // Capture a snapshot of the inputs the agent passed in for this service call so the
            // test can later assert the FunctionResultContent flowed back to the model.
            capturedInputs.Add(new List<ChatMessage>(messages));

            int index = Interlocked.Increment(ref chatCallIndex) - 1;
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

        ChatClientAgent agent = new(
            mockChatClient,
            instructions: "You are a weather agent.",
            name: "WeatherAgent",
            tools: [approvalTool]);

        // Arrange — single-agent workflow. The AIAgent is auto-promoted to an ExecutorBinding
        // via the implicit operator on ExecutorBinding.
        Workflow workflow = new WorkflowBuilder(agent).Build();

        // Arrange — JSON checkpoint manager backed by an in-memory JSON store. This mirrors
        // the OP's "JsonCheckpointStore-backed CheckpointManager.CreateJson(...)" path —
        // every checkpoint is round-tripped through the same JsonMarshaller +
        // PortableValueConverter that the OP's SQL-backed store uses, just without the
        // disk/SQL hop.
        CheckpointManager checkpointManager = CheckpointManager.CreateJson(new InMemoryJsonStore());

        InProcessExecutionEnvironment env = InProcessExecution.OffThread;
        List<ChatMessage> inputMessages = [new(ChatRole.User, "What's the weather in Amsterdam?")];

        // Act 1 — run until we see the approval request, then capture the latest checkpoint.
        ExternalRequest? firstRunRequest = null;
        CheckpointInfo? checkpoint = null;

        await using (StreamingRun firstRun = await env.WithCheckpointing(checkpointManager)
                                                      .RunStreamingAsync(workflow, inputMessages))
        {
            // Trigger an actual turn — without a TurnToken the AIAgentHostExecutor will not
            // invoke the agent. This matches the GroupChatToolApproval sample and the
            // StreamAsyncWithTurnTokenShouldExecuteWorkflow pattern in InProcessExecutionTests.
            (await firstRun.TrySendMessageAsync(new TurnToken(emitEvents: false)))
                .Should().BeTrue("the workflow should accept a TurnToken");

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
            "the ChatClientAgent + FICC pipeline should have surfaced the approval request as a workflow RequestInfoEvent");
        checkpoint.Should().NotBeNull(
            "a checkpoint should have been produced while the approval request was pending");
        chatCallIndex.Should().Be(1, "the mock chat client should have been called exactly once before the approval was requested");
        invocationCount.Should().Be(0, "the underlying tool must NOT have been invoked before the approval was granted");

        ToolApprovalRequestContent? preCheckpoint = firstRunRequest!.Data.As<ToolApprovalRequestContent>();
        preCheckpoint.Should().NotBeNull("the pending external request should carry a ToolApprovalRequestContent payload");
        preCheckpoint!.ToolCall.Should().BeOfType<FunctionCallContent>(
            "the pre-checkpoint pending request payload must already be a FunctionCallContent");

        // Act 2 — resume from the checkpoint with a brand-new env / handle so that any
        // in-process AIAgentHostExecutor instance state is gone and everything has to be
        // rehydrated from the on-disk JSON.
        ExternalRequest? resumedRequest = null;
        List<WorkflowEvent> postResumeEvents = [];

        await using (StreamingRun resumed = await env.WithCheckpointing(checkpointManager)
                                                     .ResumeStreamingAsync(workflow, checkpoint!))
        {
            using CancellationTokenSource cts = new(TimeSpan.FromSeconds(30));

            // First pass: see the re-emitted RequestInfoEvent, but don't block on it.
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts.Token))
            {
                if (evt is RequestInfoEvent requestInfo)
                {
                    resumedRequest ??= requestInfo.Request;
                }
            }

            resumedRequest.Should().NotBeNull(
                "the resumed workflow should re-emit the pending approval RequestInfoEvent");

            // The core issue #5350 assertion.
            ToolApprovalRequestContent? postResume = resumedRequest!.Data.As<ToolApprovalRequestContent>();
            postResume.Should().NotBeNull(
                "ExternalRequest.Data.As<ToolApprovalRequestContent>() should materialize the payload after a JSON-file checkpoint resume");
            postResume!.ToolCall.Should().NotBeNull("the resumed TARC must carry its ToolCall");
            postResume.ToolCall.Should().BeOfType<FunctionCallContent>(
                "after CheckpointManager.CreateJson(InMemoryJsonStore) round-trip via " +
                "ResumeStreamingAsync, ToolApprovalRequestContent.ToolCall must still be a " +
                "FunctionCallContent so that FunctionInvokingChatClient's pattern match " +
                "(`tarc.ToolCall is FunctionCallContent`) continues to fire (issue #5350).");

            FunctionCallContent resumedFcc = (FunctionCallContent)postResume.ToolCall;
            resumedFcc.Name.Should().Be(ToolName);
            resumedFcc.CallId.Should().EndWith(ToolCallId,
                "the workflow rewrites the CallId with an executor-scoped prefix, but should preserve the original tail");

            // Act 3 — send the approval response back into the resumed run and watch the
            // remaining stream. This drives FunctionInvokingChatClient through its
            // post-approval branch, where it must invoke the underlying AIFunction, append a
            // FunctionResultContent, and call the model a second time.
            ToolApprovalResponseContent approvalResponse = postResume.CreateResponse(approved: true);
            await resumed.SendResponseAsync(resumedRequest.CreateResponse(approvalResponse));

            using CancellationTokenSource cts2 = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts2.Token))
            {
                postResumeEvents.Add(evt);
            }
        }

        // Assert 3 — the tool actually got called as part of the approval round-trip, and
        // the workflow continued without raising errors.
        invocationCount.Should().Be(1,
            "approving the request should cause FunctionInvokingChatClient to invoke the wrapped AIFunction exactly once");
        chatCallIndex.Should().Be(2,
            "after the tool was invoked, FunctionInvokingChatClient should have made a second chat-client call to produce the final assistant message");
        capturedInputs.Should().HaveCount(2);
        capturedInputs[1].Should().Contain(
            m => m.Contents.OfType<FunctionResultContent>().Any(),
            "the second chat-client call must include the FunctionResultContent produced by the approved tool invocation");

        postResumeEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
            "no workflow errors should be raised when responding to the resumed approval request");
        postResumeEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty(
            "no executor failures should be raised when responding to the resumed approval request");
    }

    /// <summary>
    /// Minimal <see cref="IChatClient"/> stub for repro tests; delegates each call to a caller-supplied factory.
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

    /// <summary>
    /// Track A2 — same as the maximal repro (test #7) but with the agent inside a
    /// <c>GroupChatBuilder</c> (round-robin manager with a single participant), to rule out
    /// a group-chat-specific re-wrap or replay path that drops the
    /// <see cref="ToolApprovalRequestContent.ToolCall"/> type during the checkpoint round-trip.
    ///
    /// <para><b>Finding:</b> the <see cref="FunctionCallContent"/> type IS preserved after
    /// resume (consistent with tests #1 – #7 — the OP's hypothesis still does not reproduce
    /// in this configuration). However, sending an approval response back into the resumed
    /// group-chat workflow surfaces a <i>different</i>, real bug:
    /// <c>FunctionInvokingChatClient.ExtractAndRemoveApprovalRequestsAndResponses</c> throws
    /// <see cref="ArgumentException"/> with message
    /// <c>"An item with the same key has already been added. Key: ficc_call-1"</c>.
    /// This test pins that observed behavior so future investigation can latch onto it.</para>
    /// </summary>
    [Fact]
    public async Task Repro_5350_A2_GroupChatBuilder_WithApprovalRequiredTool_JsonCheckpointResume_PreservesFunctionCallContentAsync()
    {
        ReproHarness harness = new();
        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 4 })
            .AddParticipants(harness.Agent)
            .Build();

        await RunReproAsync(
            workflow,
            harness,
            CheckpointManager.CreateJson(new InMemoryJsonStore()),
            scenarioName: "A2 (group chat)",
            expectCleanPostApprovalCompletion: false,
            postApprovalCompletionAssertion: events =>
            {
                // A2 currently surfaces a duplicate-key crash inside FICC when the group-chat
                // workflow resumes with a pending approval request and the response arrives.
                // This assertion pins the observed misbehavior. If the upstream
                // GroupChat + AIAgentHostExecutor + FICC interaction is fixed, this test will
                // start failing here — that's intentional. The fix should then either remove
                // this assertion or convert it to a clean-completion assertion mirroring
                // test #7. TODO(#5350-followup): file a separate issue for the duplicate-key
                // crash if one does not already exist, and link it here.
                ArgumentException? duplicateKey = events
                    .OfType<WorkflowErrorEvent>()
                    .Select(e => e.Data as Exception)
                    .Select(e => e?.InnerException as ArgumentException ?? e as ArgumentException)
                    .FirstOrDefault(e => e?.Message.Contains("ficc_call-1", StringComparison.Ordinal) == true);
                duplicateKey.Should().NotBeNull(
                    "[A2 (group chat)] approving the resumed approval request currently surfaces a duplicate-key " +
                    "ArgumentException out of FunctionInvokingChatClient.ExtractAndRemoveApprovalRequestsAndResponses — " +
                    "this is a real bug, but it is NOT the bug claimed in issue #5350. The TARC.ToolCall was already " +
                    "asserted to be a FunctionCallContent above; the OP's hypothesis remains unreproduced.");
            });
    }

    /// <summary>
    /// Track A2b — same as A2, but using a <c>HandoffWorkflowBuilder</c> instead of a group
    /// chat. The initial agent is the same approval-tool-equipped <see cref="ChatClientAgent"/>
    /// as test #7; a second dummy agent is registered solely so the handoff graph has a valid
    /// peer (the mock chat client never emits a <c>handoff_to_*</c> call, so the workflow stays
    /// on the initial agent). This isolates whether anything in the handoff-specific
    /// orchestration (handoff tool injection, <c>HandoffMessagesFilter</c>, the
    /// <c>HandoffStartExecutor</c>/<c>HandoffEndExecutor</c> wrap-up) perturbs the
    /// <see cref="ToolApprovalRequestContent"/> payload across a JSON checkpoint resume.
    ///
    /// <para><b>Finding:</b> the handoff path is fully clean. The <see cref="FunctionCallContent"/>
    /// type is preserved after resume <i>and</i> approving the resumed request completes the
    /// workflow without errors and invokes the wrapped <see cref="AIFunction"/> exactly once.
    /// This is in contrast to A2 (group chat), which preserves the type but crashes on
    /// approval with a duplicate-key <see cref="ArgumentException"/> in FICC. The OP's
    /// hypothesis (<c>TARC.ToolCall is not FunctionCallContent</c>) still does not reproduce.
    /// </para>
    /// </summary>
    [Fact]
    public async Task Repro_5350_A2b_HandoffWorkflowBuilder_WithApprovalRequiredTool_JsonCheckpointResume_PreservesFunctionCallContentAndInvokesToolAsync()
    {
        ReproHarness harness = new();

        // Second agent is a no-op peer required to give the handoff graph a valid target.
        // The mock chat client only ever emits a FunctionCallContent for GetWeather, so the
        // initial agent never actually hands off; the second agent is never invoked.
        MockChatClient peerChatClient = new((messages, options) =>
            new ChatResponse(new ChatMessage(ChatRole.Assistant, "(unused peer)")));
        ChatClientAgent peerAgent = new(
            peerChatClient,
            instructions: "Unused peer agent.",
            name: "PeerAgent");

        Workflow workflow = AgentWorkflowBuilder
            .CreateHandoffBuilderWith(harness.Agent)
            .WithHandoff(harness.Agent, peerAgent)
            .Build();

        await RunReproAsync(
            workflow,
            harness,
            CheckpointManager.CreateJson(new InMemoryJsonStore()),
            scenarioName: "A2b (handoff)");
    }

    /// <summary>
    /// Track A3 — same as the maximal repro (test #7) but the checkpoint <see cref="JsonElement"/>
    /// is round-tripped through <see cref="JsonElement.GetRawText"/> + <see cref="JsonDocument.Parse(string,JsonDocumentOptions)"/>
    /// between commit and retrieve, to emulate the SQL <c>nvarchar</c> / Dapper hop in the
    /// OP's setup. This catches cases where the storage layer would only fail if it perturbed
    /// the JSON in some way (e.g. dropped metadata, re-encoded numbers), and confirms a
    /// byte-preserving string round-trip on its own is harmless.
    /// </summary>
    [Fact]
    public async Task Repro_5350_A3_StringRoundTripStore_PreservesFunctionCallContentAsync()
    {
        ReproHarness harness = new();
        Workflow workflow = new WorkflowBuilder(harness.Agent).Build();

        CheckpointManager checkpointManager = CheckpointManager.CreateJson(
            new StringRoundTripJsonStore(new InMemoryJsonStore()));

        await RunReproAsync(
            workflow,
            harness,
            checkpointManager,
            scenarioName: "A3 (string round-trip store)");
    }

    /// <summary>
    /// Track A4 — same as the maximal repro (test #7) but with a non-default
    /// <see cref="JsonSerializerOptions"/> passed as <c>customOptions</c> to
    /// <see cref="CheckpointManager.CreateJson"/>. The custom options intentionally do NOT
    /// include the polymorphism resolver chain (<c>AgentAbstractionsJsonUtilities</c> →
    /// <c>AIJsonUtilities</c>) — confirming that <c>JsonMarshaller</c>'s internal
    /// <c>WorkflowsJsonUtilities.DefaultOptions</c> chain always wins for known
    /// <see cref="AIContent"/> types and the external options cannot silently displace it.
    /// </summary>
    [Fact]
    public async Task Repro_5350_A4_CustomJsonSerializerOptions_PreservesFunctionCallContentAsync()
    {
        ReproHarness harness = new();
        Workflow workflow = new WorkflowBuilder(harness.Agent).Build();

        // Custom options that DO NOT know about AIContent / FunctionCallContent.
        JsonSerializerOptions customOptions = new(JsonSerializerDefaults.Web)
        {
            WriteIndented = true,
        };

        CheckpointManager checkpointManager = CheckpointManager.CreateJson(
            new InMemoryJsonStore(),
            customOptions);

        await RunReproAsync(
            workflow,
            harness,
            checkpointManager,
            scenarioName: "A4 (custom JsonSerializerOptions)");
    }

    /// <summary>
    /// Shared end-to-end repro driver used by tests #7, A2, A3, A4.
    /// Drives the workflow until an approval request appears, captures the latest checkpoint,
    /// disposes the run, resumes from the checkpoint, and asserts that the resumed
    /// <see cref="RequestInfoEvent"/>'s <see cref="ToolApprovalRequestContent.ToolCall"/> is
    /// still a <see cref="FunctionCallContent"/>. Then sends an approval response and asserts
    /// the wrapped <see cref="AIFunction"/> is invoked exactly once.
    /// </summary>
    private static async Task RunReproAsync(
        Workflow workflow,
        ReproHarness harness,
        CheckpointManager checkpointManager,
        string scenarioName,
        bool expectCleanPostApprovalCompletion = true,
        Action<IReadOnlyList<WorkflowEvent>>? postApprovalCompletionAssertion = null)
    {
        InProcessExecutionEnvironment env = InProcessExecution.OffThread;
        List<ChatMessage> inputMessages = [new(ChatRole.User, "What's the weather in Amsterdam?")];

        // Act 1 — run until approval request appears and capture latest checkpoint.
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

        // Act 2 — resume from checkpoint on a fresh handle.
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

            resumedRequest.Should().NotBeNull(
                $"[{scenarioName}] the resumed workflow should re-emit the pending approval RequestInfoEvent");

            ToolApprovalRequestContent? postResume = resumedRequest!.Data.As<ToolApprovalRequestContent>();
            postResume.Should().NotBeNull(
                $"[{scenarioName}] ExternalRequest.Data.As<ToolApprovalRequestContent>() should materialize the payload after JSON-checkpoint resume");
            postResume!.ToolCall.Should().NotBeNull($"[{scenarioName}] the resumed TARC must carry its ToolCall");
            postResume.ToolCall.Should().BeOfType<FunctionCallContent>(
                $"[{scenarioName}] after CheckpointManager.CreateJson round-trip via ResumeStreamingAsync, " +
                "ToolApprovalRequestContent.ToolCall must still be a FunctionCallContent so that " +
                "FunctionInvokingChatClient's pattern match (`tarc.ToolCall is FunctionCallContent`) continues to fire (issue #5350).");

            // Act 3 — approve and finish the workflow.
            ToolApprovalResponseContent approvalResponse = postResume.CreateResponse(approved: true);
            await resumed.SendResponseAsync(resumedRequest.CreateResponse(approvalResponse));

            using CancellationTokenSource cts2 = new(TimeSpan.FromSeconds(30));
            await foreach (WorkflowEvent evt in resumed.WatchStreamAsync(blockOnPendingRequest: false, cts2.Token))
            {
                postResumeEvents.Add(evt);
            }
        }

        if (expectCleanPostApprovalCompletion)
        {
            harness.InvocationCount.Should().Be(1,
                $"[{scenarioName}] approving the request should cause FunctionInvokingChatClient to invoke the wrapped AIFunction exactly once");
            postResumeEvents.OfType<WorkflowErrorEvent>().Should().BeEmpty(
                $"[{scenarioName}] no workflow errors should be raised when responding to the resumed approval request");
            postResumeEvents.OfType<ExecutorFailedEvent>().Should().BeEmpty(
                $"[{scenarioName}] no executor failures should be raised when responding to the resumed approval request");
        }

        postApprovalCompletionAssertion?.Invoke(postResumeEvents);
    }

    /// <summary>
    /// Bundles a <see cref="ChatClientAgent"/> + counting <see cref="ApprovalRequiredAIFunction"/>
    /// + <see cref="MockChatClient"/> in a single reusable harness so the four end-to-end repro
    /// variants (#7, A2, A3, A4) can share identical setup.
    /// </summary>
    private sealed class ReproHarness
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

        public ReproHarness()
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
    /// Wraps a <see cref="JsonCheckpointStore"/> and forces every <see cref="JsonElement"/> to
    /// round-trip through <c>GetRawText()</c> + <see cref="JsonDocument.Parse(string,JsonDocumentOptions)"/>
    /// during commit and again during retrieve. This emulates a Dapper-backed SQL store where
    /// the <see cref="JsonElement"/> is materialized to a string for the <c>nvarchar(max)</c>
    /// column on the way in and re-parsed on the way back out. Used by the A3 test only;
    /// the double parse-and-clone is intentionally extra work and not suitable for production use.
    /// </summary>
    private sealed class StringRoundTripJsonStore(JsonCheckpointStore inner) : JsonCheckpointStore
    {
        public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
        {
            JsonElement roundTripped = RoundTrip(value);
            return await inner.CreateCheckpointAsync(sessionId, roundTripped, parent).ConfigureAwait(false);
        }

        public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
        {
            JsonElement raw = await inner.RetrieveCheckpointAsync(sessionId, key).ConfigureAwait(false);
            return RoundTrip(raw);
        }

        public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
            => inner.RetrieveIndexAsync(sessionId, withParent);

        private static JsonElement RoundTrip(JsonElement element)
        {
            string raw = element.GetRawText();
            using JsonDocument doc = JsonDocument.Parse(raw);
            return doc.RootElement.Clone();
        }
    }
}
