// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for external input.
/// </summary>
public sealed class ExternalInputRequest : IExternalRequestEnvelope
{
    /// <summary>
    /// The source message that triggered the request for external input.
    /// </summary>
    public AgentResponse AgentResponse { get; }

    [JsonConstructor]
    internal ExternalInputRequest(AgentResponse agentResponse)
    {
        this.AgentResponse = agentResponse;
    }

    internal ExternalInputRequest(ChatMessage message)
    {
        this.AgentResponse = new AgentResponse(message);
    }

    internal ExternalInputRequest(string text)
    {
        this.AgentResponse = new AgentResponse(new ChatMessage(ChatRole.User, text));
    }

    /// <inheritdoc />
    /// <remarks>
    /// Prefers <see cref="ToolApprovalRequestContent"/> (when the workflow declared
    /// <c>requireApproval: true</c>) over <see cref="FunctionCallContent"/> so that
    /// hosts which speak the approval protocol see the approval-bearing content.
    /// </remarks>
    AIContent? IExternalRequestEnvelope.GetInnerRequestContent()
    {
        IList<ChatMessage>? messages = this.AgentResponse?.Messages;
        if (messages is null)
        {
            return null;
        }

        foreach (ChatMessage message in messages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is ToolApprovalRequestContent toolApprovalRequest)
                {
                    return toolApprovalRequest;
                }
            }
        }

        foreach (ChatMessage message in messages)
        {
            foreach (AIContent content in message.Contents)
            {
                if (content is FunctionCallContent functionCall)
                {
                    return functionCall;
                }
            }
        }

        return null;
    }

    /// <inheritdoc />
    object IExternalRequestEnvelope.CreateResponse(IList<ChatMessage> messages)
        => new ExternalInputResponse(messages);
}
