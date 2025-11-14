// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Represents errors that occur during the execution of a Purview job.
/// </summary>
/// <remarks>This exception is thrown when a Purview job encounters an error that prevents it from completing successfully.</remarks>
internal class PurviewJobException : PurviewException
{
    /// <inheritdoc/>
    public PurviewJobException(string message) : base(message)
    {
    }

    /// <inheritdoc/>
    public PurviewJobException() : base()
    {
    }

    /// <inheritdoc/>
    public PurviewJobException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
