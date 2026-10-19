// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents the response to a <see cref="ExternalInputRequest"/>.
/// </summary>
public sealed class ExternalInputResponse
{
    /// <summary>
    /// The message being provided as external input to the workflow.
    /// </summary>
    public IList<ChatMessage> Messages { get; }

    /// <summary>
    /// Gets the request id that produced this response, if available.
    /// </summary>
    [JsonInclude]
    public string? RequestId { get; internal init; }

    internal bool HasMessages => this.Messages?.Count > 0;

    /// <summary>
    /// Initializes a new instance of <see cref="ExternalInputResponse"/>.
    /// </summary>
    /// <param name="message">The external input message being provided to the workflow.</param>
    public ExternalInputResponse(ChatMessage message)
        : this([message], requestId: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of <see cref="ExternalInputResponse"/>.
    /// </summary>
    /// <param name="messages">The external input messages being provided to the workflow.</param>
    [JsonConstructor]
    public ExternalInputResponse(IList<ChatMessage> messages)
        : this(messages, requestId: null)
    {
    }

    internal ExternalInputResponse(IList<ChatMessage> messages, string? requestId)
    {
        this.Messages = messages;
        this.RequestId = requestId;
    }

}
