// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class InProcessStateTests
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
                        TState? state = await context.ReadStateAsync<TState>(stateKey.Key, stateKey.ScopeId.ScopeName)
                                                     .ConfigureAwait(false);

                        state = action(state);

                        await context.QueueStateUpdateAsync(stateKey.Key, state, stateKey.ScopeId.ScopeName);

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
               currState.Should().Be(expectedValue, because, becauseArgs);

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
        status.Should().Be(RunStatus.Idle);

        writer.Completed.Should().BeTrue();
        validator.Completed.Should().BeTrue();
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

        Checkpointed<Run> checkpointed = await InProcessExecution.RunAsync<TurnToken>(workflow, new(), CheckpointManager.Default);

        checkpointed.Checkpoints.Should().HaveCount(4);

        RunStatus status = await checkpointed.Run.GetStatusAsync();
        status.Should().Be(RunStatus.Idle);

        writer.Completed.Should().BeTrue();
        validator.Completed.Should().BeTrue();
    }

    [Fact]
    public async Task InProcessRun_StateShouldError_TwoExecutorsAsync()
    {
        ForwardMessageExecutor<TurnToken> forward = new(nameof(ForwardMessageExecutor<TurnToken>));
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

        var act = async () => await InProcessExecution.RunAsync(workflow, new TurnToken());

        var result = await act.Should()
                              .ThrowAsync("multiple writers to the same shared scope key");
    }
}
