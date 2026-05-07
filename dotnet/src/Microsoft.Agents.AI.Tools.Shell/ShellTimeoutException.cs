// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Thrown when a shell command exceeds its configured timeout.
/// </summary>
public sealed class ShellTimeoutException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="ShellTimeoutException"/> class.</summary>
    public ShellTimeoutException() { }

    /// <summary>Initializes a new instance of the <see cref="ShellTimeoutException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    public ShellTimeoutException(string message) : base(message) { }

    /// <summary>Initializes a new instance of the <see cref="ShellTimeoutException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    /// <param name="inner">The inner exception.</param>
    public ShellTimeoutException(string message, Exception inner) : base(message, inner) { }
}
