// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Represents any exception that occurs during the execution of a process workflow.
/// </summary>
public class DeclarativeWorkflowException : Exception
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeWorkflowException"/> class.
    /// </summary>
    public DeclarativeWorkflowException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeWorkflowException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    public DeclarativeWorkflowException(string? message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DeclarativeWorkflowException"/> class with a specified error message and a reference to the inner exception that is the cause of this exception.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    /// <param name="innerException">The exception that is the cause of the current exception, or a null reference if no inner exception is specified.</param>
    public DeclarativeWorkflowException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
