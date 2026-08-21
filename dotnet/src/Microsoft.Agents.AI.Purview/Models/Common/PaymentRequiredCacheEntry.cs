// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Cached tenant-level payment required state.
/// </summary>
internal sealed class PaymentRequiredCacheEntry
{
    /// <summary>
    /// Creates a new instance of <see cref="PaymentRequiredCacheEntry"/>.
    /// </summary>
    /// <param name="message">The payment required error message.</param>
    public PaymentRequiredCacheEntry(string? message)
    {
        this.Message = message;
    }

    /// <summary>
    /// The payment required error message.
    /// </summary>
    public string? Message { get; set; }
}
