// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event triggered when an executor handler fails.
/// </summary>
/// <param name="executorId">The unique identifier of the executor that has failed.</param>
/// <param name="err">The exception representing the error.</param>
public sealed class ExecutorFailedEvent(string executorId, Exception? err)
    : ExecutorEvent(executorId, data: err)
{
    /// <summary>
    /// The exception that caused the executor to fail. This may be <c>null</c> if no exception was thrown.
    /// </summary>
    public new Exception? Data => err;
}
