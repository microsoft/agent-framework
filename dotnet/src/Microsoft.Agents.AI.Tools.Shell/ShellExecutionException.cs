// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Thrown when a shell command fails to launch or the shell session is unrecoverable.
/// </summary>
public sealed class ShellExecutionException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="ShellExecutionException"/> class.</summary>
    public ShellExecutionException() { }

    /// <summary>Initializes a new instance of the <see cref="ShellExecutionException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    public ShellExecutionException(string message) : base(message) { }

    /// <summary>Initializes a new instance of the <see cref="ShellExecutionException"/> class.</summary>
    /// <param name="message">The exception message.</param>
    /// <param name="inner">The inner exception.</param>
    public ShellExecutionException(string message, Exception inner) : base(message, inner) { }
}
