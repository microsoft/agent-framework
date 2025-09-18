// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

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
        GuessNumberExecutor guessNumberExecutor = new(1, 100);
        JudgeExecutor judgeExecutor = new(42);

        // Build the workflow by connecting executors in a loop
        var workflow = new WorkflowBuilder(guessNumberExecutor)
            .AddEdge(guessNumberExecutor, judgeExecutor)
            .AddEdge(judgeExecutor, guessNumberExecutor)
            .Build<NumberSignal>();

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent workflowCompleteEvt)
            {
                Console.WriteLine($"Result: {workflowCompleteEvt}");
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
internal sealed class GuessNumberExecutor : ReflectingExecutor<GuessNumberExecutor>, IMessageHandler<NumberSignal>
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
    /// <param name="lowerBound">The initial lower bound of the guessing range.</param>
    /// <param name="upperBound">The initial upper bound of the guessing range.</param>
    public GuessNumberExecutor(int lowerBound, int upperBound)
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
}

/// <summary>
/// Executor that judges the guess and provides feedback.
/// </summary>
internal sealed class JudgeExecutor : ReflectingExecutor<JudgeExecutor>, IMessageHandler<int>
{
    private readonly int _targetNumber;
    private int _tries;

    /// <summary>
    /// Initializes a new instance of the <see cref="JudgeExecutor"/> class.
    /// </summary>
    /// <param name="targetNumber">The number to be guessed.</param>
    public JudgeExecutor(int targetNumber)
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
}
