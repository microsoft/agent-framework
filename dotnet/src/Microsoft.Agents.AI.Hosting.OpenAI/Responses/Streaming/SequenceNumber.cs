// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// Implements a sequence number generator.
/// </summary>
internal sealed class SequenceNumber
{
    private int _sequenceNumber;

    /// <summary>
    /// Gets the next sequence number.
    /// </summary>
    /// <returns>The next sequence number.</returns>
    public int Increment() => this._sequenceNumber++;
}
