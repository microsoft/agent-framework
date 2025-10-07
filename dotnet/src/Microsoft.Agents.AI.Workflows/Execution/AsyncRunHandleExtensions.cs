// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal static class AsyncRunHandleExtensions
{
    public async static ValueTask<Checkpointed<TRunType>> WithCheckpointingAsync<TRunType>(this AsyncRunHandle runHandle, Func<ValueTask<TRunType>> prepareFunc)
    {
        TRunType run = await prepareFunc().ConfigureAwait(false);
        return new Checkpointed<TRunType>(run, runHandle);
    }

    public static async ValueTask<StreamingRun> EnqueueAndStreamAsync<TInput>(this AsyncRunHandle runHandle, TInput input, CancellationToken cancellation = default)
    {
        await runHandle.EnqueueMessageAsync(input, cancellation).ConfigureAwait(false);
        return new(runHandle);
    }

    public static async ValueTask<StreamingRun> EnqueueUntypedAndStreamAsync(this AsyncRunHandle runHandle, object input, CancellationToken cancellation = default)
    {
        await runHandle.EnqueueMessageUntypedAsync(input, cancellation: cancellation).ConfigureAwait(false);
        return new(runHandle);
    }

    public static async ValueTask<Run> EnqueueAndRunAsync<TInput>(this AsyncRunHandle runHandle, TInput input, CancellationToken cancellation = default)
    {
        await runHandle.EnqueueMessageAsync(input, cancellation).ConfigureAwait(false);
        Run run = new(runHandle);

        await run.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
        return run;
    }

    public static async ValueTask<Run> EnqueueUntypedAndRunAsync(this AsyncRunHandle runHandle, object input, CancellationToken cancellation = default)
    {
        await runHandle.EnqueueMessageUntypedAsync(input, cancellation: cancellation).ConfigureAwait(false);
        Run run = new(runHandle);

        await run.RunToNextHaltAsync(cancellation).ConfigureAwait(false);
        return run;
    }
}
