// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Handles the simple form of A2A communication.
/// Is designed to process a single message conversation or a streaming conversation by returning a stream of messages.
/// </summary>
public interface IA2AMessageProcessor : IA2AAgentCardProvider
{
    /// <summary>
    /// Processes an A2A message.
    /// </summary>
    /// <param name="messageSendParams"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken);
}
