// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a token to resume or continue an operation.
/// </summary>
public class ResumptionToken
{
    private readonly byte[]? _bytes;

    /// <summary>
    /// Create a new instance of <see cref="ResumptionToken"/>.
    /// </summary>
    protected ResumptionToken() { }

    /// <summary>
    /// Create a new instance of <see cref="ResumptionToken"/>.
    /// </summary>
    protected ResumptionToken(byte[] bytes)
    {
        Throw.IfNull(bytes);

        this._bytes = bytes;
    }

    /// <summary>
    /// Create a new instance of <see cref="ResumptionToken"/> from the
    /// provided <paramref name="bytes"/>.
    /// </summary>
    /// <param name="bytes">Bytes obtained from calling <see cref="ToBytes"/>
    /// on a <see cref="ResumptionToken"/>.</param>
    /// <returns>A <see cref="ResumptionToken"/> equivalent to the one
    /// from which the original <see cref="ResumptionToken"/> bytes were
    /// obtained.
    /// </returns>
    public static ResumptionToken FromBytes(byte[] bytes) => new(bytes);

    /// <summary>
    /// Gets the bytes representing this <see cref="ResumptionToken"/>.
    /// </summary>
    /// <returns>The bytes of this <see cref="ResumptionToken"/>.</returns>
    public virtual byte[] ToBytes() => this._bytes ?? throw new InvalidOperationException("Unable to write token as bytes.");
}
