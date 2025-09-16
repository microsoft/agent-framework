// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.Interpreter;

internal sealed record class ExecutorResultMessage(string ExecutorId, object? Result = null)
{
    public static ExecutorResultMessage ThrowIfNot(object? message)
    {
        if (message is not ExecutorResultMessage executorMessage)
        {
            throw new DeclarativeActionException($"Unexpected message type: {message?.GetType().Name ?? "(null)"} (Expected: {nameof(ExecutorResultMessage)})");
        }

        return executorMessage;
    }
}
