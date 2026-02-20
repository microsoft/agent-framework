// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides context for a custom A2A response mode decision.
/// Passed to the delegate supplied to <see cref="A2AResponseMode.Dynamic(System.Func{A2AResponseDecisionContext, System.Threading.Tasks.ValueTask{bool}})"/>.
/// </summary>
public sealed class A2AResponseDecisionContext
{
    internal A2AResponseDecisionContext(MessageSendParams messageSendParams, AgentResponse agentResponse)
    {
        this.MessageSendParams = messageSendParams;
        this.AgentResponse = agentResponse;
    }

    /// <summary>
    /// Gets the parameters of the incoming A2A message that triggered this run.
    /// </summary>
    public MessageSendParams MessageSendParams { get; }

    /// <summary>
    /// Gets the response produced by the agent for the incoming message.
    /// </summary>
    public AgentResponse AgentResponse { get; }
}
