using AzureAIAgents.Models;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

public interface IAgentInvocation
{
    Task<AzureAIAgents.Models.Response> InvokeAsync(CreateResponse createResponse, AgentInvocationContext context,
        CancellationToken cancellationToken = default);

    IAsyncEnumerable<ResponseStreamEvent> InvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken = default);
}
