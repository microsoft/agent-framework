// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step2bEntryPoint
{
    public static ValueTask RunAsync()
    {
        GuessNumberExecutor guessNumber = new(1, 100);
        JudgeExecutor judge = new(42); // Let's say the target number is 42

        Workflow<NumberSignal> workflow = new WorkflowBuilder(guessNumber)
            .AddLoop(guessNumber, judge)
            .Build<NumberSignal>();

        // async foreach (var event in workflow.RunAsync(NumberSignal.Init))
        //     await Console.Out.WriteLineAsync(event);

        return CompletedValueTaskSource.Completed;
    }
}

internal enum NumberSignal
{
    Init,
    Above,
    Below,
    Matched
}

internal sealed class GuessNumberExecutor : Executor, IMessageHandler<NumberSignal, int>
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
    public async ValueTask<int> HandleAsync(NumberSignal message, IExecutionContext context)
    {
        switch (message)
        {
            case NumberSignal.Matched:
                await context.AddEventAsync(new WorkflowCompletedEvent { Data = $"Guessed the number: {this._currGuess}" })
                             .ConfigureAwait(false);
                break;

            case NumberSignal.Above:
                this.UpperBound = this._currGuess - 1;
                break;
            case NumberSignal.Below:
                this.LowerBound = this._currGuess + 1;
                break;
        }

        return this._currGuess = this.NextGuess;
    }
}

internal sealed class JudgeExecutor : Executor, IMessageHandler<int, NumberSignal>
{
    private readonly int _targetNumber;

    public JudgeExecutor(int targetNumber)
    {
        this._targetNumber = targetNumber;
    }

    public ValueTask<NumberSignal> HandleAsync(int message, IExecutionContext context)
    {
        if (message == this._targetNumber)
        {
            return CompletedValueTaskSource.FromResult(NumberSignal.Matched);
        }
        else if (message < this._targetNumber)
        {
            return CompletedValueTaskSource.FromResult(NumberSignal.Below);
        }
        else
        {
            return CompletedValueTaskSource.FromResult(NumberSignal.Above);
        }
    }
}
