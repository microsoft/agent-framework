// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step3EntryPoint
{
    public static async ValueTask<string> RunAsync(TextWriter writer)
    {
        GuessNumberExecutor guessNumber = new(1, 100);
        JudgeExecutor judge = new(42); // Let's say the target number is 42

        Workflow<NumberSignal> workflow = new WorkflowBuilder(guessNumber)
            .AddEdge(guessNumber, judge)
            .AddEdge(judge, guessNumber)
            .Build<NumberSignal>();

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init).ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
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
}

internal enum NumberSignal
{
    Init,
    Above,
    Below,
    Matched
}

internal sealed class GuessNumberExecutor : ReflectingExecutor<GuessNumberExecutor>, IMessageHandler<NumberSignal, int>
{
    public int LowerBound { get; private set; }
    public int UpperBound { get; private set; }

    public GuessNumberExecutor(int lowerBound, int upperBound)
    {
        this.LowerBound = lowerBound;
        this.UpperBound = upperBound;
    }

    private int NextGuess => (this.LowerBound + this.UpperBound) / 2;

    private int _currGuess = -1;
    public async ValueTask<int> HandleAsync(NumberSignal message, IWorkflowContext context)
    {
        switch (message)
        {
            case NumberSignal.Matched:
                await context.AddEventAsync(new WorkflowCompletedEvent($"Guessed the number: {this._currGuess}"))
                             .ConfigureAwait(false);
                break;

            case NumberSignal.Above:
                this.UpperBound = this._currGuess - 1;
                break;
            case NumberSignal.Below:
                this.LowerBound = this._currGuess + 1;
                break;
        }

        this._currGuess = this.NextGuess;
        return this._currGuess;
    }
}

internal sealed class JudgeExecutor : ReflectingExecutor<JudgeExecutor>, IMessageHandler<int, NumberSignal>
{
    private readonly int _targetNumber;

    public JudgeExecutor(int targetNumber)
    {
        this._targetNumber = targetNumber;
    }

    public async ValueTask<NumberSignal> HandleAsync(int message, IWorkflowContext context)
    {
        NumberSignal result;
        if (message == this._targetNumber)
        {
            result = NumberSignal.Matched;
        }
        else if (message < this._targetNumber)
        {
            result = NumberSignal.Below;
        }
        else
        {
            result = NumberSignal.Above;
        }

        return result;
    }
}
