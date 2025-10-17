// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Invocation;

/// <summary>
/// Exception thrown when an agent invocation fails.
/// </summary>
public class AgentInvocationException : Exception
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvocationException"/> class.
    /// </summary>
    public AgentInvocationException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvocationException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The message that describes the error.</param>
    public AgentInvocationException(string? message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvocationException"/> class with a specified error message and a reference to the inner exception that caused this exception.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    /// <param name="innerException">The exception that is the cause of the current exception, or a null reference if no inner exception is specified.</param>
    public AgentInvocationException(string? message, Exception? innerException) : base(message, innerException)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvocationException"/> class.
    /// </summary>
    /// <param name="error">The response error details.</param>
    internal AgentInvocationException(ResponseError error)
    {
        this.Error = error;
    }

    /// <summary>
    /// Gets the response error associated with this exception.
    /// </summary>
    internal ResponseError? Error { get; }
}
