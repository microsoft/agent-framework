// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Represents an exception that is thrown when the maximum number of concurrent Purview jobs has been exceeded.
/// </summary>
/// <remarks>This exception indicates that the Purview service has reached its limit for concurrent job executions.</remarks>
internal class PurviewJobLimitExceededException : PurviewJobException
{
    /// <inheritdoc/>
    public PurviewJobLimitExceededException(string message) : base(message)
    {
    }

    /// <inheritdoc/>
    public PurviewJobLimitExceededException() : base()
    {
    }

    /// <inheritdoc/>
    public PurviewJobLimitExceededException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
