// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IRunEventStream : IAsyncDisposable
{
    void Start();
    void SignalInput();

    // this cannot be cancelled
    ValueTask StopAsync();

    ValueTask<RunStatus> GetStatusAsync(CancellationToken cancellationToken = default);

    IAsyncEnumerable<WorkflowEvent> TakeEventStreamAsync(bool blockOnPendingRequest, CancellationToken cancellationToken = default);
}
