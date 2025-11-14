// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Exception thrown when an agent with the specified name has not been registered.
/// </summary>
public sealed class AgentNotRegisteredException : InvalidOperationException
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentNotRegisteredException"/> class.
    /// </summary>
    public AgentNotRegisteredException()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentNotRegisteredException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    public AgentNotRegisteredException(string? message) : base(message)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentNotRegisteredException"/> class with a specified error message
    /// and an inner exception.
    /// </summary>
    /// <param name="message">The error message that explains the reason for the exception.</param>
    /// <param name="innerException">The exception that is the cause of the current exception.</param>
    public AgentNotRegisteredException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
