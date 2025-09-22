// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;

namespace Microsoft.Agents.Workflows.Sample;

internal static class Step3EntryPoint
{
    public static Workflow<NumberSignal> WorkflowInstance
    {
        get
        {
            GuessNumberExecutor guessNumber = new(1, 100);
            JudgeExecutor judge = new(42); // Let's say the target number is 42

            return new WorkflowBuilder(guessNumber)
                .AddEdge(guessNumber, judge)
                .AddEdge(judge, guessNumber)
                .Build<NumberSignal>();
        }
    }

    public static async ValueTask<string> RunAsync(TextWriter writer)
    {
        StreamingRun run = await InProcessExecution.StreamAsync(WorkflowInstance, NumberSignal.Init).ConfigureAwait(false);

        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
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

    internal int? Tries { get; private set; }

    public JudgeExecutor(int targetNumber)
    {
        this._targetNumber = targetNumber;
    }

    public async ValueTask<NumberSignal> HandleAsync(int message, IWorkflowContext context)
    {
        this.Tries = this.Tries is int tries ? tries + 1 : 1;

        return
            message == this._targetNumber ? NumberSignal.Matched :
            message < this._targetNumber ? NumberSignal.Below :
            NumberSignal.Above;
    }

    protected internal override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        return context.QueueStateUpdateAsync("TryCount", this.Tries);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default)
    {
        this.Tries = await context.ReadStateAsync<int?>("TryCount").ConfigureAwait(false) ?? 0;
    }
}
