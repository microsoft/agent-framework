// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Orchestrates the processing of scoped content by combining protection scope, process content, and content activities operations.
/// </summary>
internal interface IScopedContentProcessor
{
    /// <summary>
    /// Process a list of messages.
    /// The list of messages should be a prompt or response.
    /// </summary>
    /// <param name="messages">A list of <see cref="ChatMessage"/> objects sent to the agent or received from the agent..</param>
    /// <param name="threadId">The thread where the messages were sent.</param>
    /// <param name="activity">An activity to indicate prompt or response.</param>
    /// <param name="purviewSettings">Purview settings containing tenant id, app name, etc.</param>
    /// <param name="userId">The user who sent the prompt or is receiving the response.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A bool indicating if the request should be blocked and the user id of the user who made the request.</returns>
    Task<(bool shouldBlock, string? userId)> ProcessMessagesAsync(IEnumerable<ChatMessage> messages, string? threadId, Activity activity, PurviewSettings purviewSettings, string? userId, CancellationToken cancellationToken);
}
