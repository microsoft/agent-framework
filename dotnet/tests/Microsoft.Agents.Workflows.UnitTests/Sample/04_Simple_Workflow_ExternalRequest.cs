// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step4EntryPoint
{
    public static Workflow<NumberSignal, string> CreateWorkflowInstance(out JudgeExecutor judge)
    {
        InputPort guessNumber = InputPort.Create<NumberSignal, int>("GuessNumber");
        judge = new(42); // Let's say the target number is 42

        return new WorkflowBuilder(guessNumber)
            .AddEdge(guessNumber, judge)
            .AddEdge(judge, guessNumber, (NumberSignal signal) => signal != NumberSignal.Matched)
            .BuildWithOutput<NumberSignal, NumberSignal, string>(judge, ComputeStreamingOutput, (s, _) => s is NumberSignal.Matched);
    }

    public static Workflow<NumberSignal, string> WorkflowInstance
    {
        get
        {
            return CreateWorkflowInstance(out _);
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer, Func<string, int> userGuessCallback)
    {
        Workflow<NumberSignal, string> workflow = WorkflowInstance;
        StreamingRun<string> handle = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init).ConfigureAwait(false);

        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    ExternalResponse response = ExecuteExternalRequest(requestInputEvt.Request, userGuessCallback, workflow.RunningOutput);
                    await handle.SendResponseAsync(response).ConfigureAwait(false);
                    break;

                case WorkflowCompletedEvent workflowCompleteEvt:
                    // The workflow has completed successfully, return the result
                    string workflowResult = workflowCompleteEvt.Data!.ToString()!;
                    writer.WriteLine($"Result: {workflowResult}");
                    return workflowResult;
                case ExecutorCompletedEvent executorCompletedEvt:
                    writer.WriteLine($"'{executorCompletedEvt.ExecutorId}: {executorCompletedEvt.Data}");
                    break;
            }
        }

        throw new InvalidOperationException("Workflow failed to yield the completion event.");
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
