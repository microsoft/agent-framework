// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Container for shared test helpers used by every orchestration-builder test class —
/// the <c>DoubleEchoAgent</c> family and the <c>RunWorkflow*</c> methods. The actual
/// test methods live in per-builder files (<c>SequentialWorkflowBuilderTests</c>,
/// <c>ConcurrentWorkflowBuilderTests</c>, <c>GroupChatWorkflowBuilderTests</c>, etc.).
/// </summary>
public static class OrchestrationTestHelpers
{
    internal class DoubleEchoAgent(string name) : AIAgent
    {
        public override string Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => new(new DoubleEchoAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => default;

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();

            var contents = messages.SelectMany(m => m.Contents).ToList();
            string id = Guid.NewGuid().ToString("N");
            yield return new AgentResponseUpdate(ChatRole.Assistant, this.Name) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
            yield return new AgentResponseUpdate(ChatRole.Assistant, contents) { AuthorName = this.Name, MessageId = id };
        }
    }

    internal sealed class DoubleEchoAgentSession() : AgentSession();

    internal sealed class DoubleEchoAgentWithBarrier(string name, StrongBox<TaskCompletionSource<bool>> barrier, StrongBox<int> remaining) : DoubleEchoAgent(name)
    {
        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            if (Interlocked.Decrement(ref remaining.Value) == 0)
            {
                barrier.Value!.SetResult(true);
            }

            await barrier.Value!.Task.ConfigureAwait(false);

            await foreach (var update in base.RunCoreStreamingAsync(messages, session, options, cancellationToken))
            {
                await Task.Yield();
                yield return update;
            }
        }
    }

    internal sealed record WorkflowRunResult(string UpdateText, List<ChatMessage>? Result, CheckpointInfo? LastCheckpoint, List<RequestInfoEvent> PendingRequests);

    internal static async Task<WorkflowRunResult> RunWorkflowCheckpointedAsync(
        Workflow workflow, List<ChatMessage> input, InProcessExecutionEnvironment environment, CheckpointInfo? fromCheckpoint = null)
    {
        await using StreamingRun run =
            fromCheckpoint != null ? await environment.ResumeStreamingAsync(workflow, fromCheckpoint)
                                   : await environment.OpenStreamingAsync(workflow);

        await run.TrySendMessageAsync(input);
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));

        return await ProcessWorkflowRunAsync(run);
    }

    internal static async Task<WorkflowRunResult> ProcessWorkflowRunAsync(StreamingRun run)
    {
        StringBuilder sb = new();
        WorkflowOutputEvent? output = null;
        CheckpointInfo? lastCheckpoint = null;

        List<RequestInfoEvent> pendingRequests = [];

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false).ConfigureAwait(false))
        {
            switch (evt)
            {
                case AgentResponseUpdateEvent responseUpdate:
                    sb.Append(responseUpdate.Data);
                    break;

                case RequestInfoEvent requestInfo:
                    pendingRequests.Add(requestInfo);
                    break;

                case WorkflowOutputEvent e:
                    output = e;
                    break;

                case WorkflowErrorEvent errorEvent:
                    Assert.Fail($"Workflow execution failed with error: {errorEvent.Exception}");
                    break;

                case SuperStepCompletedEvent stepCompleted:
                    lastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
                    break;
            }
        }

        return new(sb.ToString(), output?.As<List<ChatMessage>>(), lastCheckpoint, pendingRequests);
    }

    internal static Task<WorkflowRunResult> RunWorkflowAsync(
        Workflow workflow, List<ChatMessage> input, ExecutionEnvironment executionEnvironment = ExecutionEnvironment.InProcess_Lockstep)
        => RunWorkflowCheckpointedAsync(workflow, input, executionEnvironment.ToWorkflowExecutionEnvironment());
}
