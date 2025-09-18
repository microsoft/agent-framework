// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;

namespace WorkflowCheckpointWithHumanInTheLoopSample;

internal static class WorkflowHelper
{
    /// <summary>
    /// Get a workflow that plays a number guessing game with human-in-the-loop interaction.
    /// An input port allows the external world to provide inputs to the workflow upon requests.
    /// </summary>
    internal static Workflow<SignalWithNumber> GetWorkflow()
    {
        // Create the executors
        InputPort numberInputPort = InputPort.Create<SignalWithNumber, int>("GuessNumber");
        JudgeExecutor judgeExecutor = new(42);

        // Build the workflow by connecting executors in a loop
        return new WorkflowBuilder(numberInputPort)
            .AddEdge(numberInputPort, judgeExecutor)
            .AddEdge(judgeExecutor, numberInputPort)
            .Build<SignalWithNumber>();
    }
}

/// <summary>
/// Signals indicating if the guess was too high, too low, or an initial guess.
/// </summary>
internal enum NumberSignal
{
    Init,
    Above,
    Below,
}

/// <summary>
/// Signals used for communication between guesses and the JudgeExecutor.
/// </summary>
internal sealed class SignalWithNumber
{
    public NumberSignal Signal { get; }
    public int? Number { get; }

    public SignalWithNumber(NumberSignal signal, int? number = null)
    {
        this.Signal = signal;
        this.Number = number;
    }
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
            await context.SendMessageAsync(new SignalWithNumber(NumberSignal.Below, message)).ConfigureAwait(false);
        }
        else
        {
            await context.SendMessageAsync(new SignalWithNumber(NumberSignal.Above, message)).ConfigureAwait(false);
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
