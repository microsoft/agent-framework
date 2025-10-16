namespace Azure.AI.AgentsHosting.Ingress.Invocation;

public class AgentInvocationException(AzureAIAgents.Models.ResponseError error) : Exception
{
    public AzureAIAgents.Models.ResponseError Error { get; } = error;
}
