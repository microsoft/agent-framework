// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// Represents an agent response that contains structured output and
/// the original agent response from which the structured output was generated.
/// </summary>
internal sealed class StructuredOutputAgentResponse : AgentResponse
{
    /// <summary>
    /// Initializes a new instance of the <see cref="StructuredOutputAgentResponse"/> class.
    /// </summary>
    /// <param name="chatResponse">The <see cref="ChatResponse"/> containing the structured output.</param>
    /// <param name="agentResponse">The original <see cref="AgentResponse"/> from the inner agent.</param>
    public StructuredOutputAgentResponse(ChatResponse chatResponse, AgentResponse agentResponse) : base(chatResponse)
    {
        this.OriginalResponse = agentResponse;
    }

    /// <summary>
    /// Gets the original non-structured response from the inner agent used by chat client to produce the structured output.
    /// </summary>
    public AgentResponse OriginalResponse { get; }
}
