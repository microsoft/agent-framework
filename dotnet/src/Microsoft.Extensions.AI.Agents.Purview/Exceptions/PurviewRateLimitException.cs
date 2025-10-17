// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Purview.Exceptions;

/// <summary>
/// Exception for rate limit exceeded errors from Purview service.
/// </summary>
public class PurviewRateLimitException : PurviewServiceException
{
    /// <inheritdoc />
    public PurviewRateLimitException(string message)
        : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewRateLimitException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewRateLimitException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
