// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Exception for authentication errors related to Purview.
/// </summary>
public class PurviewAuthenticationException : PurviewException
{
    /// <inheritdoc />
    public PurviewAuthenticationException(string message)
        : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewAuthenticationException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewAuthenticationException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
