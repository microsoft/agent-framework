// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Configuration options hosting AI Agents as an Executor.
/// </summary>
public sealed class AIAgentHostOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether agent streaming update events should be emitted during execution.
    /// If <see langword="null"/>, the value will be taken from the <see cref="TurnToken"/>
    /// </summary>
    public bool? EmitAgentUpdateEvents { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether aggregated agent response events should be emitted during execution.
    /// </summary>
    public bool EmitAgentResponseEvents { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether <see cref="ToolApprovalRequestContent"/> should be intercepted and sent
    /// as a message to the workflow for handling, instead of being raised as a request.
    /// </summary>
    public bool InterceptUserInputRequests { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether <see cref="FunctionCallContent"/> without a corresponding
    /// <see cref="FunctionResultContent"/> should be intercepted and sent as a message to the workflow for handling,
    /// instead of being raised as a request.
    /// </summary>
    public bool InterceptUnterminatedFunctionCalls { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether other messages from other agents should be assigned to the
    /// <see cref="ChatRole.User"/> role during execution.
    /// </summary>
    public bool ReassignOtherAgentsAsUsers { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether incoming messages are automatically forwarded before new messages generated
    /// by the agent during its turn.
    /// </summary>
    public bool ForwardIncomingMessages { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether the complete agent response should be forwarded as a workflow message.
    /// </summary>
    /// <remarks>
    /// When enabled, downstream executors that handle <see cref="AIAgentHostResponse"/> can inspect response-level
    /// metadata such as <see cref="AgentResponse.FinishReason"/>, <see cref="AgentResponse.Usage"/>, and
    /// <see cref="AgentResponse.ResponseId"/>. Existing chat-message forwarding is unchanged.
    /// </remarks>
    public bool ForwardAgentResponse { get; set; }
}

/// <summary>
/// Represents the complete response produced by an <see cref="AIAgent"/> hosted in a workflow.
/// </summary>
/// <remarks>
/// <see cref="AIAgentHostResponse"/> is sent as a workflow message when
/// <see cref="AIAgentHostOptions.ForwardAgentResponse"/> is enabled. It allows custom downstream executors to inspect
/// response-level metadata while the existing chat-message path continues to carry portable conversation messages to
/// chat-protocol executors.
/// </remarks>
public sealed class AIAgentHostResponse
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentHostResponse"/> class.
    /// </summary>
    /// <param name="executorId">The ID of the executor that produced the response.</param>
    /// <param name="agentResponse">The complete response returned by the hosted agent.</param>
    /// <param name="fullConversation">The portable conversation context containing input messages and forwarded response messages.</param>
    /// <param name="forwardableMessages">The sanitized response messages forwarded on the chat-message path.</param>
    public AIAgentHostResponse(
        string executorId,
        AgentResponse agentResponse,
        IReadOnlyList<ChatMessage> fullConversation,
        IReadOnlyList<ChatMessage> forwardableMessages)
    {
        this.ExecutorId = Throw.IfNull(executorId);
        this.AgentResponse = Throw.IfNull(agentResponse);
        this.FullConversation = new List<ChatMessage>(Throw.IfNull(fullConversation));
        this.ForwardableMessages = new List<ChatMessage>(Throw.IfNull(forwardableMessages));
    }

    /// <summary>
    /// Gets the ID of the executor that produced the response.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// Gets the complete response returned by the hosted agent.
    /// </summary>
    public AgentResponse AgentResponse { get; }

    /// <summary>
    /// Gets the portable conversation context containing the input messages and forwarded response messages.
    /// </summary>
    public IReadOnlyList<ChatMessage> FullConversation { get; }

    /// <summary>
    /// Gets the sanitized response messages forwarded on the chat-message path.
    /// </summary>
    public IReadOnlyList<ChatMessage> ForwardableMessages { get; }
}
