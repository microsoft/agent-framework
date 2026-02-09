// Copyright (c) Microsoft. All rights reserved.
// Description: Save and resume workflow state using checkpoints and rehydration.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSamples.Checkpoints;

// <checkpoint_workflow>
/// <summary>
/// Demonstrates checkpoints for saving and restoring workflow state.
/// Key concepts: super steps, automatic checkpointing, and rehydration.
/// Uses a number guessing game to show checkpoint creation and resume.
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the workflow
        var workflow = BuildWorkflow();

        // Create checkpoint manager
        var checkpointManager = CheckpointManager.Default;
        var checkpoints = new List<CheckpointInfo>();

        // Execute the workflow and save checkpoints
        await using Checkpointed<StreamingRun> checkpointedRun = await InProcessExecution
            .StreamAsync(workflow, NumberSignal.Init, checkpointManager);

        await foreach (WorkflowEvent evt in checkpointedRun.Run.WatchStreamAsync())
        {
            if (evt is ExecutorCompletedEvent executorCompletedEvt)
            {
                Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
            }

            if (evt is SuperStepCompletedEvent superStepCompletedEvt)
            {
                CheckpointInfo? checkpoint = superStepCompletedEvt.CompletionInfo!.Checkpoint;
                if (checkpoint is not null)
                {
                    checkpoints.Add(checkpoint);
                    Console.WriteLine($"** Checkpoint created at step {checkpoints.Count}.");
                }
            }

            if (evt is WorkflowOutputEvent outputEvent)
            {
                Console.WriteLine($"Workflow completed with result: {outputEvent.Data}");
            }
        }

        // Rehydrate from a saved checkpoint
        var newWorkflow = BuildWorkflow();
        const int CheckpointIndex = 5;
        Console.WriteLine($"\n\nHydrating from checkpoint {CheckpointIndex + 1}.");
        CheckpointInfo savedCheckpoint = checkpoints[CheckpointIndex];

        await using Checkpointed<StreamingRun> newCheckpointedRun =
            await InProcessExecution.ResumeStreamAsync(newWorkflow, savedCheckpoint, checkpointManager);

        await foreach (WorkflowEvent evt in newCheckpointedRun.Run.WatchStreamAsync())
        {
            if (evt is ExecutorCompletedEvent executorCompletedEvt)
            {
                Console.WriteLine($"* Executor {executorCompletedEvt.ExecutorId} completed.");
            }

            if (evt is WorkflowOutputEvent workflowOutputEvt)
            {
                Console.WriteLine($"Workflow completed with result: {workflowOutputEvt.Data}");
            }
        }
    }
// </checkpoint_workflow>

// <checkpoint_factory>
    internal static Workflow BuildWorkflow()
    {
        GuessNumberExecutor guessNumberExecutor = new(1, 100);
        JudgeExecutor judgeExecutor = new(42);

        return new WorkflowBuilder(guessNumberExecutor)
            .AddEdge(guessNumberExecutor, judgeExecutor)
            .AddEdge(judgeExecutor, guessNumberExecutor)
            .WithOutputFrom(judgeExecutor)
            .Build();
    }
}

internal enum NumberSignal
{
    Init,
    Above,
    Below,
}
// </checkpoint_factory>

// <checkpoint_executors>
internal sealed class GuessNumberExecutor() : Executor<NumberSignal>("Guess")
{
    public int LowerBound { get; private set; }
    public int UpperBound { get; private set; }
    private const string StateKey = "GuessNumberExecutorState";

    public GuessNumberExecutor(int lowerBound, int upperBound) : this()
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

    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, (this.LowerBound, this.UpperBound), cancellationToken: cancellationToken);

    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        (this.LowerBound, this.UpperBound) = await context.ReadStateAsync<(int, int)>(StateKey, cancellationToken: cancellationToken);
}

internal sealed class JudgeExecutor() : Executor<int>("Judge")
{
    private readonly int _targetNumber;
    private int _tries;
    private const string StateKey = "JudgeExecutorState";

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
        else if (message < this._targetNumber)
        {
            await context.SendMessageAsync(NumberSignal.Below, cancellationToken: cancellationToken);
        }
        else
        {
            await context.SendMessageAsync(NumberSignal.Above, cancellationToken: cancellationToken);
        }
    }

    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, this._tries, cancellationToken: cancellationToken);

    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        this._tries = await context.ReadStateAsync<int>(StateKey, cancellationToken: cancellationToken);
}
// </checkpoint_executors>
