// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal static class AsyncRunHandleExtensions
{
    public static async ValueTask<Checkpointed<TRunType>> WithCheckpointingAsync<TRunType>(this AsyncRunHandle runHandle, Func<ValueTask<TRunType>> prepareFunc)
    {
        TRunType run = await prepareFunc().ConfigureAwait(false);
        return new Checkpointed<TRunType>(run, runHandle);
    }

    public static async ValueTask<StreamingRun> EnqueueAndStreamAsync<TInput>(this AsyncRunHandle runHandle, TInput input, CancellationToken cancellationToken = default)
    {
        await runHandle.EnqueueMessageAsync(input, cancellationToken).ConfigureAwait(false);
        return new(runHandle);
    }

    public static async ValueTask<StreamingRun> EnqueueUntypedAndStreamAsync(this AsyncRunHandle runHandle, object input, CancellationToken cancellationToken = default)
    {
        await runHandle.EnqueueMessageUntypedAsync(input, cancellationToken: cancellationToken).ConfigureAwait(false);
        return new(runHandle);
    }

    public static async ValueTask<Run> EnqueueAndRunAsync<TInput>(this AsyncRunHandle runHandle, TInput input, CancellationToken cancellationToken = default)
    {
        await runHandle.EnqueueMessageAsync(input, cancellationToken).ConfigureAwait(false);
        Run run = new(runHandle);

        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return run;
    }

    public static async ValueTask<Run> EnqueueUntypedAndRunAsync(this AsyncRunHandle runHandle, object input, CancellationToken cancellationToken = default)
    {
        await runHandle.EnqueueMessageUntypedAsync(input, cancellationToken: cancellationToken).ConfigureAwait(false);
        Run run = new(runHandle);

        await run.RunToNextHaltAsync(cancellationToken).ConfigureAwait(false);
        return run;
    }
}
