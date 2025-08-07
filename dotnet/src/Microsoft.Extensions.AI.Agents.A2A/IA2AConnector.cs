// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// A2A Communication Connector interface.
/// Implementing this allows to support A2A protocol from agentic-framework.
/// </summary>
public interface IA2AConnector
{
    /// <summary>
    /// Processes an A2A message.
    /// </summary>
    /// <param name="messageSendParams"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken);

    /// <summary>
    /// Retrieves the agent card for a given agent URL.
    /// </summary>
    /// <param name="agentPath"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
    Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken);
}
