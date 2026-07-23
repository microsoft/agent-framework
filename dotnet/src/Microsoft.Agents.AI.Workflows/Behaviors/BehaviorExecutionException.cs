// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Behaviors;

/// <summary>
/// Exception thrown when a behavior fails during execution.
/// </summary>
public sealed class BehaviorExecutionException : Exception
{
    /// <summary>
    /// Initializes a new instance of the <see cref="BehaviorExecutionException"/> class.
    /// </summary>
    public BehaviorExecutionException()
        : base("Error executing behavior")
    {
        this.BehaviorType = string.Empty;
        this.Stage = string.Empty;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="BehaviorExecutionException"/> class with a specified error message.
    /// </summary>
    /// <param name="message">The error message.</param>
    public BehaviorExecutionException(string message)
        : base(message)
    {
        this.BehaviorType = string.Empty;
        this.Stage = string.Empty;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="BehaviorExecutionException"/> class with a specified error message and inner exception.
    /// </summary>
    /// <param name="message">The error message.</param>
    /// <param name="innerException">The exception that caused this exception.</param>
    public BehaviorExecutionException(string message, Exception innerException)
        : base(message, innerException)
    {
        this.BehaviorType = string.Empty;
        this.Stage = string.Empty;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="BehaviorExecutionException"/> class.
    /// </summary>
    /// <param name="behaviorType">The type name of the behavior that failed.</param>
    /// <param name="stage">The stage at which the behavior failed.</param>
    /// <param name="innerException">The exception that caused the behavior to fail.</param>
    public BehaviorExecutionException(string behaviorType, string stage, Exception innerException)
        : base($"Error executing behavior '{behaviorType}' at stage '{stage}'", innerException)
    {
        Throw.IfNull(innerException);
        this.BehaviorType = Throw.IfNullOrEmpty(behaviorType);
        this.Stage = Throw.IfNullOrEmpty(stage);
    }

    /// <summary>
    /// Gets the type name of the behavior that failed.
    /// </summary>
    public string BehaviorType { get; }

    /// <summary>
    /// Gets the stage at which the behavior failed.
    /// </summary>
    public string Stage { get; }
}
