using System;

namespace Azure.AI.AgentsHosting.Ingress.Invocation;

/// <summary>
/// Exception thrown when an agent invocation fails.
/// </summary>
#pragma warning disable RCS1194 // Implement exception constructors
public class AgentInvocationException : Exception
#pragma warning restore RCS1194
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInvocationException"/> class.
    /// </summary>
    /// <param name="error">The response error details.</param>
    public AgentInvocationException(AzureAIAgents.Models.ResponseError error)
    {
        this.Error = error;
    }

    /// <summary>
    /// Gets the response error associated with this exception.
    /// </summary>
    public AzureAIAgents.Models.ResponseError Error { get; }
}
