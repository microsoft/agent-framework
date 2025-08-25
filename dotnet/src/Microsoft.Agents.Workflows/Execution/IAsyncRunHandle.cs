// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class RunUpdate(RunStatus runStatus, params WorkflowEvent[] events)
{
    public RunStatus RunStatus { get; } = runStatus;
    public IReadOnlyList<WorkflowEvent> Events { get; } = events;
}

internal interface IAsyncRunHandle
{
    ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellation = default);

    // TODO: lockstep mode?
    IAsyncEnumerable<WorkflowEvent> ForwardEventsAsync(bool breakOnHalt, CancellationToken cancellation = default);

    ValueTask<bool> IsValidInputTypeAsync<T>(CancellationToken cancellation = default);
    ValueTask<bool> EnqueueMessageAsync<T>(T message, CancellationToken cancellation = default) where T : notnull;
    ValueTask EnqueueResponseAsync(ExternalResponse response, CancellationToken cancellation = default);
}

internal interface IRunHandleWithOutput<TOutput>
{
    IAsyncRunHandle RunHandle { get; }
    ValueTask<TOutput?> GetRunningOutputAsync(CancellationToken cancellation = default);
}
