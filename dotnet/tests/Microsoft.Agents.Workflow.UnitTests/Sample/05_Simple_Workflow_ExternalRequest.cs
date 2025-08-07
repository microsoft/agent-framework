// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step5EntryPoint
{
    public static async ValueTask<string> RunAsync(TextWriter writer, Func<string, int> userGuessCallback)
    {
        InputPort guessNumber = new("GuessNumber", typeof(NumberSignal), typeof(int));
        JudgeExecutor judge = new(42); // Let's say the target number is 42

        Workflow<NumberSignal, string> workflow = new WorkflowBuilder(guessNumber)
            .AddEdge(guessNumber, judge)
            .AddEdge(judge, guessNumber, (message) => message is NumberSignal signal && signal != NumberSignal.Matched)
            .BuildWithOutput<NumberSignal, string>(judge, ComputeStreamingOutput, (NumberSignal s, string? _) => s == NumberSignal.Matched);

        LocalRunner<NumberSignal, string> runner = new(workflow);
        StreamingExecutionHandle<string> handle = await runner.StreamAsync(NumberSignal.Init).ConfigureAwait(false);

        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case RequestInputEvent requestInputEvt:
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

        throw new InvalidOperationException("Workflow failed to yield the completion event.");
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
