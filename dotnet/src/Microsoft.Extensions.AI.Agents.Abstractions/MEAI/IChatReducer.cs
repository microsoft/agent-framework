// Copyright (c) Microsoft. All rights reserved.

// WARNING:
// This interface has been temporarily copied here from MEAI, since it is in the MEAI code base but not shipped yet.
// This file is not intended to be modified.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a reducer capable of shrinking the size of a list of chat messages.
/// </summary>
public interface IChatReducer
{
    /// <summary>Reduces the size of a list of chat messages.</summary>
    /// <param name="messages">The messages to reduce.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>The new list of messages.</returns>
    Task<IEnumerable<ChatMessage>> ReduceAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken);
}
