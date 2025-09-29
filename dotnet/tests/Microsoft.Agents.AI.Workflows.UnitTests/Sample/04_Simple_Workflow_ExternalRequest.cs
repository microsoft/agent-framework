// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step4EntryPoint
{
    internal const string JudgeId = "Judge";

    public static Workflow CreateWorkflowInstance(out JudgeExecutor judge)
    {
        RequestPort guessNumber = RequestPort.Create<NumberSignal, int>("GuessNumber");
        judge = new(JudgeId, 42); // Let's say the target number is 42

        return new WorkflowBuilder(guessNumber)
            .AddEdge(guessNumber, judge)
            .AddEdge(judge, guessNumber, (NumberSignal signal) => signal != NumberSignal.Matched)
            .WithOutputFrom(judge)
            .Build();
    }

    public static ValueTask<Workflow<NumberSignal>?> GetPromotedWorklowInstanceAsync()
    {
        Workflow workflow = CreateWorkflowInstance(out _);
        return workflow.TryPromoteAsync<NumberSignal>();
    }

    public static Workflow WorkflowInstance
    {
        get
        {
            return CreateWorkflowInstance(out _);
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer, Func<string, int> userGuessCallback)
    {
        NumberSignal signal = NumberSignal.Init;
        string? prompt = UpdatePrompt(null, signal);

        Workflow workflow = WorkflowInstance;
        StreamingRun handle = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init).ConfigureAwait(false);

        List<ExternalRequest> requests = [];
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case WorkflowOutputEvent outputEvent:
                    switch (outputEvent.SourceId)
                    {
                        case JudgeId:
                            if (!outputEvent.Is<NumberSignal>())
                            {
                                throw new InvalidOperationException($"Unexpected output type {outputEvent.Data!.GetType()}");
                            }

                            signal = outputEvent.As<NumberSignal?>()!.Value;
                            prompt = UpdatePrompt(prompt, signal);
                            break;
                    }

                    break;
                case RequestInfoEvent requestInputEvt:
                    requests.Add(requestInputEvt.Request);
                    break;

                case SuperStepCompletedEvent stepCompletedEvent:
                    foreach (ExternalRequest request in requests)
                    {
                        ExternalResponse response = ExecuteExternalRequest(request, userGuessCallback, prompt);
                        await handle.SendResponseAsync(response).ConfigureAwait(false);
                    }
                    requests.Clear();
                    break;

                case ExecutorCompletedEvent executorCompletedEvt:
                    writer.WriteLine($"'{executorCompletedEvt.ExecutorId}: {executorCompletedEvt.Data}");
                    break;
            }
        }

        writer.WriteLine($"Result: {prompt}");
        return prompt!;
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
    /// <param name="runningResult"></param>
    /// <param name="signal"></param>
    /// <returns></returns>
    internal static string? UpdatePrompt(string? runningResult, NumberSignal signal)
    {
        return signal switch
        {
            NumberSignal.Matched => "You guessed correctly! You Win!",
            NumberSignal.Above => "Your guess was too high. Try again.",
            NumberSignal.Below => "Your guess was too low. Try again.",

            _ => runningResult
        };
    }
}
