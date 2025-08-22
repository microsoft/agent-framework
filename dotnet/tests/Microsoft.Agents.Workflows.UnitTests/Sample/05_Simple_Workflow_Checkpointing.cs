// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step5EntryPoint
{
    private static CheckpointManager CheckpointManager { get; } = new();

    public static async ValueTask<string> RunAsync(TextWriter writer, Func<string, int> userGuessCallback)
    {
        Workflow<NumberSignal, string> workflow = Step4EntryPoint.CreateWorkflowInstance(out JudgeExecutor judge);
        Checkpointed<StreamingRun<string>> checkpointed =
            await InProcessExecution.StreamAsync(workflow, NumberSignal.Init, CheckpointManager)
                                    .ConfigureAwait(false);

        List<CheckpointInfo> checkpoints = new();
        CancellationTokenSource cancellationSource = new();

        StreamingRun<string> handle = checkpointed.Run;
        string? result = await RunStreamToHaltOrMaxStepAsync(6).ConfigureAwait(false);

        result.Should().BeNull();
        checkpoints.Should().HaveCount(6, "we should have two checkpoints, one for each step");
        judge.Tries.Should().Be(2);

        await checkpointed.RestoreCheckpointAsync(checkpoints[2], CancellationToken.None).ConfigureAwait(false);
        judge.Tries.Should().Be(1);

        cancellationSource.Dispose();
        cancellationSource = new();

        checkpoints.Clear();
        result = await RunStreamToHaltOrMaxStepAsync().ConfigureAwait(false);

        result.Should().NotBeNull();
        checkpoints.Should().HaveCount(6);

        cancellationSource.Dispose();

        return result;

        async ValueTask<string?> RunStreamToHaltOrMaxStepAsync(int? maxStep = null)
        {
            await foreach (WorkflowEvent evt in handle.WatchStreamAsync(cancellationSource.Token).ConfigureAwait(false))
            {
                switch (evt)
                {
                    case SuperStepCompletedEvent stepCompletedEvt:
                        CheckpointInfo? checkpoint = stepCompletedEvt.CompletionInfo!.Checkpoint;
                        if (checkpoint != null)
                        {
                            checkpoints.Add(checkpoint);
                        }

                        if (maxStep.HasValue && stepCompletedEvt.StepNumber >= maxStep.Value - 1)
                        {
                            cancellationSource.Cancel();
                        }
                        break;
                    case RequestInfoEvent requestInputEvt:
                        ExternalResponse response = ExecuteExternalRequest(requestInputEvt.Request, userGuessCallback, workflow.RunningOutput);
                        await handle.SendResponseAsync(response).ConfigureAwait(false);
                        break;
                    case WorkflowCompletedEvent workflowCompleteEvt:
                        // The workflow has completed successfully, return the result
                        string workflowResult = workflowCompleteEvt.Data!.ToString()!;
                        writer.WriteLine($"Result: {workflowResult}");
                        return workflowResult;
                    case ExecutorCompleteEvent executorCompleteEvt:
                        writer.WriteLine($"'{executorCompleteEvt.ExecutorId}: {executorCompleteEvt.Data}");
                        break;
                }
            }

            if (cancellationSource.IsCancellationRequested)
            {
                return null;
            }

            throw new InvalidOperationException("Workflow failed to yield the completion event.");
        }
    }

    private static ExternalResponse ExecuteExternalRequest(
        ExternalRequest request,
        Func<string, int> userGuessCallback,
        string? runningState)
    {
        object result = request.Port.Id switch
        {
            "GuessNumber" => userGuessCallback(runningState ?? "Guess the number."),
            _ => throw new NotSupportedException($"Request {request.Port.Id} is not supported")
        };

        return request.CreateResponse(result);
    }

    /// <summary>
    /// This converts the incoming <see cref="NumberSignal"/> from the judge to a status text that can be displayed
    /// to the user.
    /// </summary>
    /// <remarks>
    /// This works correctly timing-wise because both the <see cref="StreamingAggregator{TInput, TOutput}"/> and the
    /// <see cref="InputPort"/> are one edge from the <see cref="JudgeExecutor"/> (see the workflow definition in the
    /// <see cref="RunAsync"/> method). That means they will get the <see cref="NumberSignal"/> at the same time (one
    /// SuperStep after the Judge has generated it.)
    /// </remarks>
    /// <param name="signal"></param>
    /// <param name="runningResult"></param>
    /// <returns></returns>
    private static string ComputeStreamingOutput(NumberSignal signal, string? runningResult)
    {
        return signal switch
        {
            NumberSignal.Matched => "You guessed correctly! You Win!",
            NumberSignal.Above => "Your guess was too high. Try again.",
            NumberSignal.Below => "Your guess was too low. Try again.",

            _ => runningResult ?? string.Empty
        };
    }
}
