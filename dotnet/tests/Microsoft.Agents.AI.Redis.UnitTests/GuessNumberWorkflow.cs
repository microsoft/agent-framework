// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Redis.UnitTests;

/// <summary>
/// A two-executor number guessing loop whose executors keep state in checkpoints, used to run a real workflow on the store.
/// </summary>
internal static class GuessNumberWorkflow
{
    public const int Target = 42;

    public static Workflow Build()
    {
        GuessNumberExecutor guesser = new();
        JudgeExecutor judge = new();
        return new WorkflowBuilder(guesser)
            .AddEdge(guesser, judge)
            .AddEdge(judge, guesser)
            .WithOutputFrom(judge)
            .Build();
    }
}

internal enum NumberSignal
{
    Init,
    Above,
    Below,
}

internal sealed record GuessBounds(int Lower, int Upper);

[SendsMessage(typeof(int))]
internal sealed class GuessNumberExecutor() : Executor<NumberSignal>("Guess")
{
    private const string StateKey = "bounds";
    private GuessBounds _bounds = new(1, 100);

    private int NextGuess => (this._bounds.Lower + this._bounds.Upper) / 2;

    public override async ValueTask HandleAsync(NumberSignal message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._bounds = message switch
        {
            NumberSignal.Above => this._bounds with { Upper = this.NextGuess - 1 },
            NumberSignal.Below => this._bounds with { Lower = this.NextGuess + 1 },
            _ => this._bounds,
        };

        await context.SendMessageAsync(this.NextGuess, cancellationToken: cancellationToken);
    }

    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, this._bounds, cancellationToken: cancellationToken);

    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        this._bounds = await context.ReadStateAsync<GuessBounds>(StateKey, cancellationToken: cancellationToken) ?? this._bounds;
}

[SendsMessage(typeof(NumberSignal))]
[YieldsOutput(typeof(string))]
internal sealed class JudgeExecutor() : Executor<int>("Judge")
{
    private const string StateKey = "tries";
    private int _tries;

    public override async ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._tries++;
        if (message == GuessNumberWorkflow.Target)
        {
            await context.YieldOutputAsync($"{GuessNumberWorkflow.Target} found in {this._tries} tries", cancellationToken: cancellationToken);
        }
        else
        {
            await context.SendMessageAsync(message < GuessNumberWorkflow.Target ? NumberSignal.Below : NumberSignal.Above, cancellationToken: cancellationToken);
        }
    }

    protected override ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        context.QueueStateUpdateAsync(StateKey, this._tries, cancellationToken: cancellationToken);

    protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
        this._tries = await context.ReadStateAsync<int>(StateKey, cancellationToken: cancellationToken);
}
