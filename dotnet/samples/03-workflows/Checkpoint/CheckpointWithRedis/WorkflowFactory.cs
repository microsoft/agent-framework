// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowCheckpointWithRedisSample;

internal static class WorkflowFactory
{
    /// <summary>
    /// Get a workflow that plays a number guessing game with checkpointing support.
    /// The workflow consists of two executors that are connected in a feedback loop:
    /// 1. GuessNumberExecutor: Makes a guess based on the current known bounds.
    /// 2. JudgeExecutor: Evaluates the guess and provides feedback.
    /// The workflow continues until the correct number is guessed.
    /// </summary>
    internal static Workflow BuildWorkflow()
    {
        GuessNumberExecutor guessNumberExecutor = new();
        JudgeExecutor judgeExecutor = new(42);

        return new WorkflowBuilder(guessNumberExecutor)
            .AddEdge(guessNumberExecutor, judgeExecutor)
            .AddEdge(judgeExecutor, guessNumberExecutor)
            .WithOutputFrom(judgeExecutor)
            .Build();
    }
}

/// <summary>
/// Signals used for communication between GuessNumberExecutor and JudgeExecutor.
/// </summary>
internal enum NumberSignal
{
    Init,
    Above,
    Below,
}

/// <summary>
/// The guessing range. Executor state is stored in the checkpoints as JSON.
/// </summary>
internal sealed record GuessRange(int LowerBound, int UpperBound);

/// <summary>
/// Executor that makes a guess based on the current bounds.
/// </summary>
[SendsMessage(typeof(int))]
internal sealed class GuessNumberExecutor() : Executor<NumberSignal>("Guess")
{
    private const string StateKey = "GuessNumberExecutorState";

    private GuessRange _range = new(1, 100);

    private int NextGuess => (this._range.LowerBound + this._range.UpperBound) / 2;

    public override async ValueTask HandleAsync(NumberSignal message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._range = message switch
        {
            NumberSignal.Above => this._range with { UpperBound = this.NextGuess - 1 },
            NumberSignal.Below => this._range with { LowerBound = this.NextGuess + 1 },
            _ => this._range,
        };

        await context.SendMessageAsync(this.NextGuess, cancellationToken: cancellationToken);
    }

    /// <summary>
    /// Checkpoint the current state of the executor.
    /// </summary>
    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, this._range, cancellationToken: cancellationToken);

    /// <summary>
    /// Restore the state of the executor from a checkpoint.
    /// </summary>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        this._range = await context.ReadStateAsync<GuessRange>(StateKey, cancellationToken: cancellationToken) ?? this._range;
}

/// <summary>
/// Executor that judges the guess and provides feedback.
/// </summary>
[SendsMessage(typeof(NumberSignal))]
[YieldsOutput(typeof(string))]
internal sealed class JudgeExecutor() : Executor<int>("Judge")
{
    private const string StateKey = "JudgeExecutorState";

    private readonly int _targetNumber;
    private int _tries;

    /// <summary>
    /// Initializes a new instance of the <see cref="JudgeExecutor"/> class.
    /// </summary>
    /// <param name="targetNumber">The number to be guessed.</param>
    public JudgeExecutor(int targetNumber) : this()
    {
        this._targetNumber = targetNumber;
    }

    public override async ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._tries++;
        if (message == this._targetNumber)
        {
            await context.YieldOutputAsync($"{this._targetNumber} found in {this._tries} tries!", cancellationToken: cancellationToken);
        }
        else
        {
            await context.SendMessageAsync(message < this._targetNumber ? NumberSignal.Below : NumberSignal.Above, cancellationToken: cancellationToken);
        }
    }

    /// <summary>
    /// Checkpoint the current state of the executor.
    /// </summary>
    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, this._tries, cancellationToken: cancellationToken);

    /// <summary>
    /// Restore the state of the executor from a checkpoint.
    /// </summary>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        this._tries = await context.ReadStateAsync<int>(StateKey, cancellationToken: cancellationToken);
}
