// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Event triggered when an executor handler fails.
/// </summary>
/// <param name="executorId">The unique identifier of the executor that has failed.</param>
/// <param name="err">The exception representing the error.</param>
public sealed class ExecutorFailureEvent(string executorId, Exception? err) : ExecutorEvent(executorId, data: err);
