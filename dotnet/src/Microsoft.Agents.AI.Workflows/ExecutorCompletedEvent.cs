// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when an executor handler has completed.
/// </summary>
/// <param name="executorId">The unique identifier of the executor that has completed.</param>
/// <param name="result">The result produced by the executor upon completion, or <c>null</c> if no result is available.</param>
public sealed class ExecutorCompletedEvent(string executorId, object? result) : ExecutorEvent(executorId, data: result);
