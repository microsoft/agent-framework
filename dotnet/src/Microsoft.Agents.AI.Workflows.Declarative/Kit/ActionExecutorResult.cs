// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Message sent to initiate a transition to another <see cref="Executor"/>.
/// </summary>
public sealed record class ActionExecutorResult
{
    /// <summary>
    /// The identifier of the <see cref="Executor"/> that produced this message.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// The result of the action, if any provided.
    /// </summary>
    public object? Result { get; }

    internal ActionExecutorResult(string executorId, object? result = null)
    {
        this.ExecutorId = executorId;
        this.Result = result;
    }

    internal static ActionExecutorResult ThrowIfNot(object? message)
    {
        if (message is not ActionExecutorResult executorMessage)
        {
            throw new DeclarativeActionException($"Unexpected message type: {message?.GetType().Name ?? "(null)"} (Expected: {nameof(ActionExecutorResult)})");
        }

        return executorMessage;
    }
}
