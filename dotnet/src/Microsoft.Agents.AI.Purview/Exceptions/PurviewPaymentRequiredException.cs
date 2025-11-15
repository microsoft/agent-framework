// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Exception for payment required errors related to Purview.
/// </summary>
public class PurviewPaymentRequiredException : PurviewException
{
    /// <inheritdoc />
    public PurviewPaymentRequiredException(string message) : base(message)
    {
    }

    /// <inheritdoc />
    public PurviewPaymentRequiredException() : base()
    {
    }

    /// <inheritdoc />
    public PurviewPaymentRequiredException(string? message, Exception? innerException) : base(message, innerException)
    {
    }
}
