// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowLoopSample;

/// <summary>
/// This sample demonstrates a simple number guessing game using a workflow with looping behavior.
///
/// The workflow consists of two executors that are connected in a feedback loop:
/// 1. GuessNumberExecutor: Makes a guess based on the current known bounds.
/// 2. JudgeExecutor: Evaluates the guess and provides feedback.
/// The workflow continues until the correct number is guessed.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Create the executors
        GuessNumberExecutor guessNumberExecutor = new("GuessNumber", 1, 100);
        JudgeExecutor judgeExecutor = new("Judge", 42);

        // Build the workflow by connecting executors in a loop
        var workflow = await new WorkflowBuilder(guessNumberExecutor)
            .AddEdge(guessNumberExecutor, judgeExecutor)
            .AddEdge(judgeExecutor, guessNumberExecutor)
            .WithOutputFrom(judgeExecutor)
            .BuildAsync<NumberSignal>();

        // Execute the workflow
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is WorkflowOutputEvent outputEvent)
            {
                Console.WriteLine($"Result: {outputEvent}");
            }
        }
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
internal sealed class GuessNumberExecutor : Executor<NumberSignal>
{
    /// <summary>
    /// The lower bound of the guessing range.
    /// </summary>
    public int LowerBound { get; private set; }

    /// <summary>
    /// The upper bound of the guessing range.
    /// </summary>
    public int UpperBound { get; private set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="GuessNumberExecutor"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="lowerBound">The initial lower bound of the guessing range.</param>
    /// <param name="upperBound">The initial upper bound of the guessing range.</param>
    public GuessNumberExecutor(string id, int lowerBound, int upperBound) : base(id)
    {
        this.LowerBound = lowerBound;
        this.UpperBound = upperBound;
    }

    private int NextGuess => (this.LowerBound + this.UpperBound) / 2;

    public override async ValueTask HandleAsync(NumberSignal message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        switch (message)
        {
            case NumberSignal.Init:
                await context.SendMessageAsync(this.NextGuess, cancellationToken: cancellationToken);
                break;
            case NumberSignal.Above:
                this.UpperBound = this.NextGuess - 1;
                await context.SendMessageAsync(this.NextGuess, cancellationToken: cancellationToken);
                break;
            case NumberSignal.Below:
                this.LowerBound = this.NextGuess + 1;
                await context.SendMessageAsync(this.NextGuess, cancellationToken: cancellationToken);
                break;
        }
    }
}

/// <summary>
/// Executor that judges the guess and provides feedback.
/// </summary>
internal sealed class JudgeExecutor : Executor<int>
{
    private readonly int _targetNumber;
    private int _tries;

    /// <summary>
    /// Initializes a new instance of the <see cref="JudgeExecutor"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="targetNumber">The number to be guessed.</param>
    public JudgeExecutor(string id, int targetNumber) : base(id)
    {
        this._targetNumber = targetNumber;
    }

    public override async ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._tries++;
        if (message == this._targetNumber)
        {
            await context.YieldOutputAsync($"{this._targetNumber} found in {this._tries} tries!", cancellationToken)
                         ;
        }
        else if (message < this._targetNumber)
        {
            await context.SendMessageAsync(NumberSignal.Below, cancellationToken: cancellationToken);
        }
        else
        {
            await context.SendMessageAsync(NumberSignal.Above, cancellationToken: cancellationToken);
        }
    }
}
