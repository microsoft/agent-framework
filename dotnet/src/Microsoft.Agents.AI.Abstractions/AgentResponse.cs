// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the response to an <see cref="AIAgent"/> run request, containing messages and metadata about the interaction.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AgentResponse"/> provides one or more response messages and metadata about the response.
/// A typical response will contain a single message, however a response may contain multiple messages
/// in a variety of scenarios. For example, if the agent internally invokes functions or tools, performs
/// RAG retrievals or has other complex logic, a single run by the agent may produce many messages showing
/// the intermediate progress that the agent made towards producing the agent result.
/// </para>
/// <para>
/// To get the text result of the response, use the <see cref="Text"/> property or simply call <see cref="ToString()"/> on the <see cref="AgentResponse"/>.
/// </para>
/// </remarks>
public class AgentResponse
{
    /// <summary>The response messages.</summary>
    private IList<ChatMessage>? _messages;

    /// <summary>Initializes a new instance of the <see cref="AgentResponse"/> class.</summary>
    public AgentResponse()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="AgentResponse"/> class.</summary>
    /// <param name="message">The response message to include in this response.</param>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public AgentResponse(ChatMessage message)
    {
        _ = Throw.IfNull(message);

        this.Messages.Add(message);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponse"/> class from an existing <see cref="ChatResponse"/>.
    /// </summary>
    /// <param name="response">The <see cref="ChatResponse"/> from which to populate this <see cref="AgentResponse"/>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor creates an agent response that wraps an existing <see cref="ChatResponse"/>, preserving all
    /// metadata and storing the original response in <see cref="RawRepresentation"/> for access to
    /// the underlying implementation details.
    /// </remarks>
    public AgentResponse(ChatResponse response)
    {
        _ = Throw.IfNull(response);

        this.AdditionalProperties = response.AdditionalProperties;
        this.CreatedAt = response.CreatedAt;
        this.Messages = response.Messages;
        this.RawRepresentation = response;
        this.ResponseId = response.ResponseId;
        this.Usage = response.Usage;
        this.ContinuationToken = response.ContinuationToken;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponse"/> class from an existing <see cref="AgentResponse"/>.
    /// </summary>
    /// <param name="response">The <see cref="AgentResponse"/> from which to copy properties.</param>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// This constructor creates a copy of an existing agent response, preserving all
    /// metadata and storing the original response in <see cref="RawRepresentation"/> for access to
    /// the underlying implementation details.
    /// </remarks>
    protected AgentResponse(AgentResponse response)
    {
        _ = Throw.IfNull(response);

        this.AdditionalProperties = response.AdditionalProperties;
        this.CreatedAt = response.CreatedAt;
        this.Messages = response.Messages;
        this.RawRepresentation = response;
        this.ResponseId = response.ResponseId;
        this.Usage = response.Usage;
        this.ContinuationToken = response.ContinuationToken;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentResponse"/> class with the specified collection of messages.
    /// </summary>
    /// <param name="messages">The collection of response messages, or <see langword="null"/> to create an empty response.</param>
    public AgentResponse(IList<ChatMessage>? messages)
    {
        this._messages = messages;
    }

    /// <summary>
    /// Gets or sets the collection of messages to be represented by this response.
    /// </summary>
    /// <value>
    /// A collection of <see cref="ChatMessage"/> instances representing the agent's response.
    /// If the backing collection is <see langword="null"/>, accessing this property will create an empty list.
    /// </value>
    /// <remarks>
    /// <para>
    /// This property provides access to all messages generated during the agent's execution. While most
    /// responses contain a single assistant message, complex agent behaviors may produce multiple messages
    /// showing intermediate steps, function calls, or different types of content.
    /// </para>
    /// <para>
    /// The collection is mutable and can be modified after creation. Setting this property to <see langword="null"/>
    /// will cause subsequent access to return an empty list.
    /// </para>
    /// </remarks>
    [AllowNull]
    public IList<ChatMessage> Messages
    {
        get => this._messages ??= new List<ChatMessage>(1);
        set => this._messages = value;
    }

    /// <summary>
    /// Gets the concatenated text content of all messages in this response.
    /// </summary>
    /// <value>
    /// A string containing the combined text from all <see cref="TextContent"/> instances
    /// across all messages in <see cref="Messages"/>, or an empty string if no text content is present.
    /// </value>
    /// <remarks>
    /// This property provides a convenient way to access the textual response without needing to
    /// iterate through individual messages and content items. Non-text content is ignored.
    /// </remarks>
    [JsonIgnore]
    public string Text => this._messages?.ConcatText() ?? string.Empty;

    /// <summary>
    /// Gets or sets the identifier of the agent that generated this response.
    /// </summary>
    /// <value>
    /// A unique string identifier for the agent, or <see langword="null"/> if not specified.
    /// </value>
    /// <remarks>
    /// This identifier helps track which agent generated the response in multi-agent scenarios
    /// or for debugging and telemetry purposes.
    /// </remarks>
    public string? AgentId { get; set; }

    /// <summary>
    /// Gets or sets the unique identifier for this specific response.
    /// </summary>
    /// <value>
    /// A unique string identifier for this response instance, or <see langword="null"/> if not assigned.
    /// </value>
    public string? ResponseId { get; set; }

    /// <summary>
    /// Gets or sets the continuation token for getting the result of a background agent response.
    /// </summary>
    /// <remarks>
    /// <see cref="AIAgent"/> implementations that support background responses will return
    /// a continuation token if background responses are allowed in <see cref="AgentRunOptions.AllowBackgroundResponses"/>
    /// and the result of the response has not been obtained yet. If the response has completed and the result has been obtained,
    /// the token will be <see langword="null"/>.
    /// <para>
    /// This property should be used in conjunction with <see cref="AgentRunOptions.ContinuationToken"/> to
    /// continue to poll for the completion of the response. Pass this token to
    /// <see cref="AgentRunOptions.ContinuationToken"/> on subsequent calls to <see cref="AIAgent.RunAsync(AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>
    /// to poll for completion.
    /// </para>
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
    public ResponseContinuationToken? ContinuationToken { get; set; }

    /// <summary>
    /// Gets or sets the timestamp indicating when this response was created.
    /// </summary>
    /// <value>
    /// A <see cref="DateTimeOffset"/> representing when the response was generated,
    /// or <see langword="null"/> if not specified.
    /// </value>
    /// <remarks>
    /// The creation timestamp is useful for auditing, logging, and understanding
    /// the chronology of agentic interactions.
    /// </remarks>
    public DateTimeOffset? CreatedAt { get; set; }

    /// <summary>
    /// Gets or sets the resource usage information for generating this response.
    /// </summary>
    /// <value>
    /// A <see cref="UsageDetails"/> instance containing token counts and other usage metrics,
    /// or <see langword="null"/> if usage information is not available.
    /// </value>
    public UsageDetails? Usage { get; set; }

    /// <summary>Gets or sets the raw representation of the run response from an underlying implementation.</summary>
    /// <remarks>
    /// If a <see cref="AgentResponse"/> is created to represent some underlying object from another object
    /// model, this property can be used to store that original object. This can be useful for debugging or
    /// for enabling a consumer to access the underlying object model if needed.
    /// </remarks>
    [JsonIgnore]
    public object? RawRepresentation { get; set; }

    /// <summary>
    /// Gets or sets additional properties associated with this response.
    /// </summary>
    /// <value>
    /// An <see cref="AdditionalPropertiesDictionary"/> containing custom properties,
    /// or <see langword="null"/> if no additional properties are present.
    /// </value>
    /// <remarks>
    /// Additional properties provide a way to include custom metadata or provider-specific
    /// information that doesn't fit into the standard response schema. This is useful for
    /// preserving implementation-specific details or extending the response with custom data.
    /// </remarks>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <inheritdoc />
    public override string ToString() => this.Text;

    /// <summary>
    /// Converts this <see cref="AgentResponse"/> into a collection of <see cref="AgentResponseUpdate"/> instances
    /// suitable for streaming scenarios.
    /// </summary>
    /// <returns>
    /// An array of <see cref="AgentResponseUpdate"/> instances that collectively represent
    /// the same information as this response.
    /// </returns>
    /// <remarks>
    /// <para>
    /// This method is useful for converting complete responses back into streaming format,
    /// which may be needed for scenarios that require uniform handling of both streaming
    /// and non-streaming agent responses.
    /// </para>
    /// <para>
    /// Each message in <see cref="Messages"/> becomes a separate update, and usage information
    /// is included as an additional update if present. The order of updates preserves the
    /// original message sequence.
    /// </para>
    /// </remarks>
    public AgentResponseUpdate[] ToAgentResponseUpdates()
    {
        AgentResponseUpdate? extra = null;
        if (this.AdditionalProperties is not null || this.Usage is not null)
        {
            extra = new AgentResponseUpdate
            {
                AdditionalProperties = this.AdditionalProperties,
            };

            if (this.Usage is { } usage)
            {
                extra.Contents.Add(new UsageContent(usage));
            }
        }

        int messageCount = this._messages?.Count ?? 0;
        var updates = new AgentResponseUpdate[messageCount + (extra is not null ? 1 : 0)];

        int i;
        for (i = 0; i < messageCount; i++)
        {
            ChatMessage message = this._messages![i];
            updates[i] = new AgentResponseUpdate
            {
                AdditionalProperties = message.AdditionalProperties,
                AuthorName = message.AuthorName,
                Contents = message.Contents,
                RawRepresentation = message.RawRepresentation,
                Role = message.Role,

                AgentId = this.AgentId,
                ResponseId = this.ResponseId,
                MessageId = message.MessageId,
                CreatedAt = this.CreatedAt,
            };
        }

        if (extra is not null)
        {
            updates[i] = extra;
        }

        return updates;
    }
}
