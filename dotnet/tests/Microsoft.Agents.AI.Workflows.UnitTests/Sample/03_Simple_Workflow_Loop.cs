// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Agents.AI.Workflows.Reflection;
using Microsoft.Agents.AI.Workflows.UnitTests;

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

    public static async ValueTask<string> RunAsync(TextWriter writer, ExecutionMode executionMode)
    {
        InProcessExecutionEnvironment env = executionMode.GetEnvironment();
        StreamingRun run = await env.StreamAsync(WorkflowInstance, NumberSignal.Init).ConfigureAwait(false);

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

    public GuessNumberExecutor(string id, int lowerBound, int upperBound) : base(id, new ExecutorOptions { AutoYieldOutputHandlerResultObject = false })
    {
        this.LowerBound = lowerBound;
        this.UpperBound = upperBound;
    }

    private int NextGuess => (this.LowerBound + this.UpperBound) / 2;

    private int _currGuess = -1;
    public async ValueTask<int> HandleAsync(NumberSignal message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        switch (message)
        {
            case NumberSignal.Matched:
                await context.YieldOutputAsync($"Guessed the number: {this._currGuess}", cancellationToken)
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

internal sealed class JudgeExecutor : ReflectingExecutor<JudgeExecutor>, IMessageHandler<int, NumberSignal>, IResettableExecutor
{
    private readonly int _targetNumber;

    internal int? Tries { get; private set; }

    public JudgeExecutor(string id, int targetNumber) : base(id)
    {
        this._targetNumber = targetNumber;
    }

    public async ValueTask<NumberSignal> HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this.Tries = this.Tries is int tries ? tries + 1 : 1;

        return
            message == this._targetNumber ? NumberSignal.Matched :
            message < this._targetNumber ? NumberSignal.Below :
            NumberSignal.Above;
    }

    protected internal override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return context.QueueStateUpdateAsync("TryCount", this.Tries, cancellationToken: cancellationToken);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this.Tries = await context.ReadStateAsync<int?>("TryCount", cancellationToken: cancellationToken).ConfigureAwait(false) ?? 0;
    }

    public ValueTask ResetAsync()
    {
        this.Tries = null;
        return default;
    }
}
