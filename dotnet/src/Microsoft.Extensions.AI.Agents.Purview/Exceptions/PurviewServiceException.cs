// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Purview.Exceptions;

/// <summary>
/// General base exception type for Purview service errors.
/// </summary>
public class PurviewServiceException : Exception
{
    /// <inheritdoc />
    public PurviewServiceException(string message)
        : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewServiceException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewServiceException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
