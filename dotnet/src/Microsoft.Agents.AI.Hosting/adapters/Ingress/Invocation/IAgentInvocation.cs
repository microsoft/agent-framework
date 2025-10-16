using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

/// <summary>
/// Defines the interface for agent invocation operations.
/// </summary>
public interface IAgentInvocation
{
    /// <summary>
    /// Invokes the agent asynchronously.
    /// </summary>
    /// <param name="createResponse">The create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A task representing the response.</returns>
    Task<AzureAIAgents.Models.Response> InvokeAsync(CreateResponse createResponse, AgentInvocationContext context,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Invokes the agent asynchronously with streaming response.
    /// </summary>
    /// <param name="createResponse">The create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>An async enumerable of response stream events.</returns>
    IAsyncEnumerable<ResponseStreamEvent> InvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken = default);
}
