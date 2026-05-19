// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
}
