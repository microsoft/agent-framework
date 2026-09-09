// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public partial class InProcessStateTests
{
    private sealed class TurnToken
    {
        public int Count { get; }

        public TurnToken() : this(0)
        { }

        private TurnToken(int count)
        {
            this.Count = count;
        }

        public TurnToken Next => new(this.Count + 1);
    }

    private sealed class StateTestExecutor<TState> : TestingExecutor<TurnToken, TurnToken>
    {
        private static Func<TurnToken, IWorkflowContext, CancellationToken, ValueTask<TurnToken>>[] WrapActions(ScopeKey stateKey, Func<TState?, TState?>[] stateActions)
        {
            Func<TurnToken, IWorkflowContext, CancellationToken, ValueTask<TurnToken>>[] result
                = new Func<TurnToken, IWorkflowContext, CancellationToken, ValueTask<TurnToken>>[stateActions.Length];

            for (int i = 0; i < stateActions.Length; i++)
            {
                result[i] = CreateWrapper(stateActions[i]);
            }

            return result;

            Func<TurnToken, IWorkflowContext, CancellationToken, ValueTask<TurnToken>> CreateWrapper(Func<TState?, TState?> action)
            {
                return
                    async (turn, context, cancellation) =>
                    {
                        TState? state = await context.ReadStateAsync<TState>(stateKey.Key, stateKey.ScopeId.ScopeName, cancellation)
                                                     .ConfigureAwait(false);

                        state = action(state);

                        await context.QueueStateUpdateAsync(stateKey.Key, state, stateKey.ScopeId.ScopeName, cancellation);

                        return turn.Next;
                    };
            }
        }

        public ScopeKey StateKey { get; }

        public StateTestExecutor(ScopeKey stateKey, bool loop = false, params Func<TState?, TState?>[] stateActions)
            : base(stateKey.ScopeId.ExecutorId, loop, WrapActions(stateKey, stateActions))
        {
            this.StateKey = stateKey;
        }
    }

    private static Func<int?, int?> CreateOrIncrement(int defaultValue = default)
        => currState => currState.HasValue ? currState + 1 : defaultValue;

    private static Func<int?, int?> ValidateState(int expectedValue, string? because = null, params object[] becauseArgs)
        => currState =>
           {
               Assert.Equal(expectedValue, currState);

               return currState;
           };

    private static Func<object?, bool> MaxTurns(int maxTurns)
        => maybeTurn => maybeTurn is not TurnToken turn || turn.Count < maxTurns;

    [Fact]
    public async Task InProcessRun_StateShouldPersist_NotCheckpointedAsync()
    {
        StateTestExecutor<int?> writer = new(
                new ScopeKey("Writer", "TestScope", "TestKey"),
                loop: false,
                CreateOrIncrement(),
                CreateOrIncrement()
            );

        StateTestExecutor<int?> validator = new(
                new ScopeKey("Validator", "TestScope", "TestKey"),
                loop: false,
                ValidateState(0),
                ValidateState(1)
            );

        Workflow workflow =
            new WorkflowBuilder(writer)
                .AddEdge(writer, validator, MaxTurns(4))
                .AddEdge(validator, writer, MaxTurns(4)).Build();

        Run run = await InProcessExecution.RunAsync<TurnToken>(workflow, new());

        RunStatus status = await run.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        Assert.True(writer.Completed);
        Assert.True(validator.Completed);
    }

    [Fact]
    public async Task InProcessRun_StateShouldPersist_CheckpointedAsync()
    {
        StateTestExecutor<int?> writer = new(
                new ScopeKey("Writer", "TestScope", "TestKey"),
                loop: false,
                CreateOrIncrement(),
                CreateOrIncrement()
            );

        StateTestExecutor<int?> validator = new(
                new ScopeKey("Validator", "TestScope", "TestKey"),
                loop: false,
                ValidateState(0),
                ValidateState(1)
            );

        Workflow workflow =
            new WorkflowBuilder(writer)
                .AddEdge(writer, validator, MaxTurns(4))
                .AddEdge(validator, writer, MaxTurns(4)).Build();

        Run checkpointed = await InProcessExecution.RunAsync<TurnToken>(workflow, new(), CheckpointManager.Default);

        Assert.Equal(4, checkpointed.Checkpoints.Count);

        RunStatus status = await checkpointed.GetStatusAsync();
        Assert.Equal(RunStatus.Idle, status);

        Assert.True(writer.Completed);
        Assert.True(validator.Completed);
    }

    [Fact]
    public async Task InProcessRun_StateShouldError_TwoExecutorsAsync()
    {
        ForwardMessageExecutor<TurnToken> forward = new(nameof(ForwardMessageExecutor<>));
        using StateTestExecutor<int?> testExecutor = new(
                new ScopeKey("StateTestExecutor", "TestScope", "TestKey"),
                loop: false,
                CreateOrIncrement()
            );

        using StateTestExecutor<int?> testExecutor2 = new(
                new ScopeKey("StateTestExecutor2", "TestScope", "TestKey"),
                loop: false,
                CreateOrIncrement()
            );

        Workflow workflow =
            new WorkflowBuilder(forward)
                .AddFanOutEdge(forward, targets: [testExecutor, testExecutor2])
                .Build();

        Run runWithFailure = await InProcessExecution.RunAsync(workflow, new TurnToken());

        bool hadFailure = false;
        foreach (WorkflowEvent evt in runWithFailure.NewEvents)
        {
            if (evt is WorkflowErrorEvent errorEvent)
            {
                Assert.False(hadFailure);
                hadFailure = true;

                InvalidOperationException exception = Assert.IsType<InvalidOperationException>(errorEvent.Data);
                Assert.Contains("TestKey", exception.Message);
            }
        }

        Assert.True(hadFailure);

        //var act = async () => await InProcessExecution.RunAsync(workflow, new TurnToken());
        //var result = await act assertion
        //                      .ThrowAsync("multiple writers to the same shared scope key");
    }
}
