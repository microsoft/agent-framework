// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step5EntryPoint
{
    public static async ValueTask<string> RunAsync(TextWriter writer, Func<string, int> userGuessCallback, bool rehydrateToRestore = false, CheckpointManager? checkpointManager = null)
    {
        Dictionary<CheckpointInfo, (NumberSignal signal, string? prompt)> checkpointedOutputs = new();

        NumberSignal signal = NumberSignal.Init;
        string? prompt = Step4EntryPoint.UpdatePrompt(null, signal);

        checkpointManager ??= CheckpointManager.Default;

        Workflow workflow = Step4EntryPoint.CreateWorkflowInstance(out JudgeExecutor judge);
        Checkpointed<StreamingRun> checkpointed =
            await InProcessExecution.StreamAsync(workflow, NumberSignal.Init, checkpointManager)
                                    .ConfigureAwait(false);

        List<CheckpointInfo> checkpoints = [];
        CancellationTokenSource cancellationSource = new();

        StreamingRun handle = checkpointed.Run;
        string? result = await RunStreamToHaltOrMaxStepAsync(maxStep: 6).ConfigureAwait(false);

        result.Should().BeNull();
        checkpoints.Should().HaveCount(6, "we should have two checkpoints, one for each step");
        judge.Tries.Should().Be(2);

        CheckpointInfo targetCheckpoint = checkpoints[2];

        if (rehydrateToRestore)
        {
            await handle.EndRunAsync().ConfigureAwait(false);

            checkpointed = await InProcessExecution.ResumeStreamAsync(workflow, targetCheckpoint, checkpointManager, runId: handle.RunId, cancellationToken: CancellationToken.None)
                                                   .ConfigureAwait(false);
            handle = checkpointed.Run;
        }
        else
        {
            await checkpointed.RestoreCheckpointAsync(checkpoints[2], CancellationToken.None).ConfigureAwait(false);
        }

        (signal, prompt) = checkpointedOutputs[targetCheckpoint];

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
            List<ExternalRequest> requests = [];
            await foreach (WorkflowEvent evt in handle.WatchStreamAsync(cancellationSource.Token).ConfigureAwait(false))
            {
                switch (evt)
                {
                    case WorkflowOutputEvent outputEvent:
                        switch (outputEvent.SourceId)
                        {
                            case Step4EntryPoint.JudgeId:
                                if (!outputEvent.Is<NumberSignal>())
                                {
                                    throw new InvalidOperationException($"Unexpected output type {outputEvent.Data!.GetType()}");
                                }

                                signal = outputEvent.As<NumberSignal?>()!.Value;
                                prompt = Step4EntryPoint.UpdatePrompt(null, signal);
                                break;
                        }

                        break;

                    case RequestInfoEvent requestInputEvt:
                        requests.Add(requestInputEvt.Request);
                        break;

                    case SuperStepCompletedEvent stepCompletedEvt:
                        CheckpointInfo? checkpoint = stepCompletedEvt.CompletionInfo!.Checkpoint;
                        if (checkpoint is not null)
                        {
                            checkpoints.Add(checkpoint);

                            checkpointedOutputs[checkpoint] = (signal, prompt);
                        }

                        if (maxStep.HasValue && stepCompletedEvt.StepNumber >= maxStep.Value - 1)
                        {
                            cancellationSource.Cancel();
                        }
                        else
                        {
                            foreach (ExternalRequest request in requests)
                            {
                                ExternalResponse response = ExecuteExternalRequest(request, userGuessCallback, prompt);
                                await handle.SendResponseAsync(response).ConfigureAwait(false);
                            }

                            requests.Clear();
                        }
                        break;

                    case ExecutorCompletedEvent executorCompleteEvt:
                        writer.WriteLine($"'{executorCompleteEvt.ExecutorId}: {executorCompleteEvt.Data}");
                        break;
                }
            }

            if (cancellationSource.IsCancellationRequested)
            {
                return null;
            }

            writer.WriteLine($"Result: {prompt}");
            return prompt!;
        }
    }

    private static ExternalResponse ExecuteExternalRequest(
        ExternalRequest request,
        Func<string, int> userGuessCallback,
        string? runningState)
    {
        object result = request.PortInfo.PortId switch
        {
            "GuessNumber" => userGuessCallback(runningState ?? "Guess the number."),
            _ => throw new NotSupportedException($"Request {request.PortInfo.PortId} is not supported")
        };

        return request.CreateResponse(result);
    }
}
