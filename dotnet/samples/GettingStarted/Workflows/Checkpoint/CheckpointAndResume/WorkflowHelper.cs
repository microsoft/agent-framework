// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace WorkflowCheckpointAndResumeSample;

internal static class WorkflowHelper
{
    /// <summary>
    /// Get a workflow that plays a number guessing game with checkpointing support.
    /// The workflow consists of two executors that are connected in a feedback loop:
    /// 1. GuessNumberExecutor: Makes a guess based on the current known bounds.
    /// 2. JudgeExecutor: Evaluates the guess and provides feedback.
    /// The workflow continues until the correct number is guessed.
    /// </summary>
    internal static Workflow<NumberSignal> GetWorkflow()
    {
        // Create the executors
        GuessNumberExecutor guessNumberExecutor = new(1, 100);
        JudgeExecutor judgeExecutor = new(42);

        // Build the workflow by connecting executors in a loop
        return new WorkflowBuilder(guessNumberExecutor)
            .AddEdge(guessNumberExecutor, judgeExecutor)
            .AddEdge(judgeExecutor, guessNumberExecutor)
            .Build<NumberSignal>();
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
/// Executor that makes a guess based on the current bounds.
/// </summary>
internal sealed class GuessNumberExecutor() : ReflectingExecutor<GuessNumberExecutor>("Guess"), IMessageHandler<NumberSignal>
{
    /// <summary>
    /// The lower bound of the guessing range.
    /// </summary>
    public int LowerBound { get; private set; }

    /// <summary>
    /// The upper bound of the guessing range.
    /// </summary>
    public int UpperBound { get; private set; }

    private const string StateKey = "GuessNumberExecutorState";

    /// <summary>
    /// Initializes a new instance of the <see cref="GuessNumberExecutor"/> class.
    /// </summary>
    /// <param name="lowerBound">The initial lower bound of the guessing range.</param>
    /// <param name="upperBound">The initial upper bound of the guessing range.</param>
    public GuessNumberExecutor(int lowerBound, int upperBound) : this()
    {
        this.LowerBound = lowerBound;
        this.UpperBound = upperBound;
    }

    private int NextGuess => (this.LowerBound + this.UpperBound) / 2;

    public async ValueTask HandleAsync(NumberSignal message, IWorkflowContext context)
    {
        switch (message)
        {
            case NumberSignal.Init:
                await context.SendMessageAsync(this.NextGuess).ConfigureAwait(false);
                break;
            case NumberSignal.Above:
                this.UpperBound = this.NextGuess - 1;
                await context.SendMessageAsync(this.NextGuess).ConfigureAwait(false);
                break;
            case NumberSignal.Below:
                this.LowerBound = this.NextGuess + 1;
                await context.SendMessageAsync(this.NextGuess).ConfigureAwait(false);
                break;
        }
    }

    /// <summary>
    /// Checkpoint the current state of the executor.
    /// This must be overridden to save any state that is needed to resume the executor.
    /// </summary>
    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default) =>
        context.QueueStateUpdateAsync(StateKey, (this.LowerBound, this.UpperBound));

    /// <summary>
    /// Restore the state of the executor from a checkpoint.
    /// This must be overridden to restore any state that was saved during checkpointing.
    /// </summary>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default) =>
        (this.LowerBound, this.UpperBound) = await context.ReadStateAsync<(int, int)>(StateKey).ConfigureAwait(false);
}

/// <summary>
/// Executor that judges the guess and provides feedback.
/// </summary>
internal sealed class JudgeExecutor() : ReflectingExecutor<JudgeExecutor>("Judge"), IMessageHandler<int>
{
    private readonly int _targetNumber;
    private int _tries;
    private const string StateKey = "JudgeExecutorState";

    /// <summary>
    /// Initializes a new instance of the <see cref="JudgeExecutor"/> class.
    /// </summary>
    /// <param name="targetNumber">The number to be guessed.</param>
    public JudgeExecutor(int targetNumber) : this()
    {
        this._targetNumber = targetNumber;
    }

    public async ValueTask HandleAsync(int message, IWorkflowContext context)
    {
        this._tries++;
        if (message == this._targetNumber)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"{this._targetNumber} found in {this._tries} tries!"))
                         .ConfigureAwait(false);
        }
        else if (message < this._targetNumber)
        {
            await context.SendMessageAsync(NumberSignal.Below).ConfigureAwait(false);
        }
        else
        {
            await context.SendMessageAsync(NumberSignal.Above).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Checkpoint the current state of the executor.
    /// This must be overridden to save any state that is needed to resume the executor.
    /// </summary>
    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellation = default) =>
        context.QueueStateUpdateAsync(StateKey, this._tries);

    /// <summary>
    /// Restore the state of the executor from a checkpoint.
    /// This must be overridden to restore any state that was saved during checkpointing.
    /// </summary>
    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellation = default) =>
        this._tries = await context.ReadStateAsync<int>(StateKey).ConfigureAwait(false);
}
