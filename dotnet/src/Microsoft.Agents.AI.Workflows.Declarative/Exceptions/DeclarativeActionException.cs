// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Represents an exception that occurs during action execution.
/// </summary>
public sealed class DeclarativeActionException : DeclarativeWorkflowException
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeActionException"/> class.
    /// </summary>
    public DeclarativeActionException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeActionException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    public DeclarativeActionException(string? message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeActionException"/> class with a specified error message and a reference to the inner exception that is the cause of this exception.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    /// <param name="innerException">The exception that is the cause of the current exception, or a null reference if no inner exception is specified.</param>
    public DeclarativeActionException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
