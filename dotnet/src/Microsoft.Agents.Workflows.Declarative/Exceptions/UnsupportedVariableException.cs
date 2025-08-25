// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Represents an exception that occurs when the specific scope is invalid.
/// </summary>
public sealed class UnsupportedVariableException : DeclarativeWorkflowException
{
    /// <summary>
    /// Initializes a new instance of the <see cref="UnsupportedVariableException"/> class.
    /// </summary>
    public UnsupportedVariableException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="UnsupportedVariableException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    public UnsupportedVariableException(string? message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="UnsupportedVariableException"/> class with a specified error message and a reference to the inner exception that is the cause of this exception.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    /// <param name="innerException">The exception that is the cause of the current exception, or a null reference if no inner exception is specified.</param>
    public UnsupportedVariableException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
