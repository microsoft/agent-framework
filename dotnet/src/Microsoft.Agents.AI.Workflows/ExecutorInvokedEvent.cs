// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when an executor handler is invoked.
/// </summary>
/// <param name="executorId">The unique identifier of the executor being invoked.</param>
/// <param name="message">The invocation message.</param>
public sealed class ExecutorInvokedEvent(string executorId, object message) : ExecutorEvent(executorId, data: message);
