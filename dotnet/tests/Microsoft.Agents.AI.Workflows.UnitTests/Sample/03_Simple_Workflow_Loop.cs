// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Reflection;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step3EntryPoint
{
    public static Workflow WorkflowInstance
    {
        get
        {
            GuessNumberExecutor guessNumber = new("GuessNumber", 1, 100);
            JudgeExecutor judge = new("Judge", 42); // Let's say the target number is 42

            return new WorkflowBuilder(guessNumber)
                .AddEdge(guessNumber, judge)
                .AddEdge(judge, guessNumber)
                .WithOutputFrom(guessNumber)
                .Build();
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        StreamingRun run = await environment.StreamAsync(WorkflowInstance, NumberSignal.Init).ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case WorkflowOutputEvent workflowOutputEvt:
                    // The workflow has completed successfully, return the result
                    string workflowResult = workflowOutputEvt.As<string>()!;
                    writer.WriteLine($"Result: {workflowResult}");
                    return workflowResult;
                case ExecutorCompletedEvent executorCompletedEvt:
                    writer.WriteLine($"'{executorCompletedEvt.ExecutorId}: {executorCompletedEvt.Data}");
                    break;
            }
        }

        throw new InvalidOperationException("Workflow failed to yield an output.");
    }
}

internal sealed record TryCount(int Tries);

internal sealed record NumberBounds(int LowerBound, int UpperBound)
{
    public int CurrGuess => (this.LowerBound + this.UpperBound) / 2;

    public NumberBounds ForAboveHint() => this with { UpperBound = this.CurrGuess - 1 };
    public NumberBounds ForBelowHint() => this with { LowerBound = this.CurrGuess + 1 };
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
    private readonly int _initialLowerBound;
    private readonly int _initialUpperBound;

    public GuessNumberExecutor(string id, int lowerBound, int upperBound) : base(id, new ExecutorOptions { AutoYieldOutputHandlerResultObject = false }, declareCrossRunShareable: true)
    {
        if (lowerBound >= upperBound)
        {
            throw new ArgumentOutOfRangeException(nameof(lowerBound), "Lower bound must be less than upper bound.");
        }

        this._initialLowerBound = lowerBound;
        this._initialUpperBound = upperBound;
    }

    public async ValueTask<int> HandleAsync(NumberSignal message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        NumberBounds bounds = await context.ReadStateAsync<NumberBounds>(nameof(NumberBounds), cancellationToken: cancellationToken)
                                           .ConfigureAwait(false)
                              ?? new NumberBounds(this._initialLowerBound, this._initialUpperBound);

        switch (message)
        {
            case NumberSignal.Matched:
                await context.YieldOutputAsync($"Guessed the number: {bounds.CurrGuess}", cancellationToken)
                             .ConfigureAwait(false);
                break;

            case NumberSignal.Above:
                bounds = bounds.ForAboveHint();
                break;
            case NumberSignal.Below:
                bounds = bounds.ForBelowHint();
                break;
        }

        await context.QueueStateUpdateAsync(nameof(NumberBounds), bounds, cancellationToken: cancellationToken).ConfigureAwait(false);

        return bounds.CurrGuess;
    }
}

internal sealed class JudgeExecutor : ReflectingExecutor<JudgeExecutor>, IMessageHandler<int, NumberSignal>
{
    private readonly int _targetNumber;

    public JudgeExecutor(string id, int targetNumber) : base(id, declareCrossRunShareable: true)
    {
        this._targetNumber = targetNumber;
    }

    public async ValueTask<NumberSignal> HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // This works properly because the default when unset is 0, and we increment before use.
        int tries = await context.ReadStateAsync<int>("TryCount", cancellationToken: cancellationToken).ConfigureAwait(false) + 1;
        await context.YieldOutputAsync(new TryCount(tries), cancellationToken);

        return
            message == this._targetNumber ? NumberSignal.Matched :
            message < this._targetNumber ? NumberSignal.Below :
            NumberSignal.Above;
    }
}
