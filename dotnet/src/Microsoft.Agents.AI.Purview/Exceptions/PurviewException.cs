// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// General base exception type for Purview service errors.
/// </summary>
public class PurviewException : Exception
{
    /// <inheritdoc />
    public PurviewException(string message)
        : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
