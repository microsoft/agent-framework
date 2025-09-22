// Copyright (c) Microsoft. All rights reserved.

using System;
#if NET9_0_OR_GREATER
using System.Buffers;
#endif
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;

#if NET9_0_OR_GREATER
using System.Text;
#endif
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Shared.Diagnostics;

#pragma warning disable S109 // Magic numbers should not be used
#pragma warning disable S1121 // Assignments should not be made from within sub-expressions

namespace Microsoft.Extensions.AI.Agents;

/// <summary>Represents the response to an Agent run request.</summary>
/// <remarks>
/// <see cref="AgentRunResponse"/> provides one or more response messages and metadata about the response.
/// A typical response will contain a single message, however a response may contain multiple messages
/// in a variety of scenarios. For example, if the agent internally invokes functions or tools, performs
/// RAG retrievals or has other complex logic, a single run by the agent may produce many messages showing
/// the intermediate progress that the agent made towards producing the agent result.
/// </remarks>
public class AgentRunResponse
{
    /// <summary>The response messages.</summary>
    private IList<ChatMessage>? _messages;

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponse"/> class.</summary>
    public AgentRunResponse()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponse"/> class.</summary>
    /// <param name="message">The response message.</param>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public AgentRunResponse(ChatMessage message)
    {
        _ = Throw.IfNull(message);

        this.Messages.Add(message);
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponse"/> class.</summary>
    /// <param name="response">The <see cref="ChatResponse"/> from which to seed this <see cref="AgentRunResponse"/>.</param>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public AgentRunResponse(ChatResponse response)
    {
        _ = Throw.IfNull(response);

        this.AdditionalProperties = response.AdditionalProperties;
        this.CreatedAt = response.CreatedAt;
        this.Messages = response.Messages;
        this.RawRepresentation = response;
        this.ResponseId = response.ResponseId;
        this.Usage = response.Usage;
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponse"/> class.</summary>
    /// <param name="messages">The response messages.</param>
    public AgentRunResponse(IList<ChatMessage>? messages)
    {
        this._messages = messages;
    }

    /// <summary>Gets or sets the agent response messages.</summary>
    [AllowNull]
    public IList<ChatMessage> Messages
    {
        get => this._messages ??= new List<ChatMessage>(1);
        set => this._messages = value;
    }

    /// <summary>Gets the text of the response.</summary>
    /// <remarks>
    /// This property concatenates the <see cref="ChatMessage.Text"/> of all <see cref="ChatMessage"/>
    /// instances in <see cref="Messages"/>.
    /// </remarks>
    [JsonIgnore]
    public string Text => this._messages?.ConcatText() ?? string.Empty;

    /// <summary>Gets the user input requests associated with the response.</summary>
    /// <remarks>
    /// This property concatenates all <see cref="UserInputRequestContent"/> instances in the response.
    /// </remarks>
    [JsonIgnore]
    public IEnumerable<UserInputRequestContent> UserInputRequests => this._messages?.SelectMany(x => x.Contents).OfType<UserInputRequestContent>() ?? [];

    /// <summary>Gets or sets the ID of the agent that produced the response.</summary>
    public string? AgentId { get; set; }

    /// <summary>Gets or sets the ID of the agent response.</summary>
    public string? ResponseId { get; set; }

    /// <summary>Gets or sets a timestamp for the run response.</summary>
    public DateTimeOffset? CreatedAt { get; set; }

    /// <summary>Gets or sets usage details for the run response.</summary>
    /// <remarks>
    /// Where the agent run response is produced via many model invocations, this
    /// usage is an aggregation of the usage for all these model invocations.
    /// </remarks>
    public UsageDetails? Usage { get; set; }

    /// <summary>Gets or sets the raw representation of the run response from an underlying implementation.</summary>
    /// <remarks>
    /// If a <see cref="AgentRunResponse"/> is created to represent some underlying object from another object
    /// model, this property can be used to store that original object. This can be useful for debugging or
    /// for enabling a consumer to access the underlying object model if needed.
    /// </remarks>
    [JsonIgnore]
    public object? RawRepresentation { get; set; }

    /// <summary>Gets or sets any additional properties associated with the run response.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <inheritdoc />
    public override string ToString() => this.Text;

    /// <summary>Creates an array of <see cref="AgentRunResponseUpdate" /> instances that represent this <see cref="AgentRunResponse" />.</summary>
    /// <returns>An array of <see cref="AgentRunResponseUpdate" /> instances that may be used to represent this <see cref="AgentRunResponse" />.</returns>
    public AgentRunResponseUpdate[] ToAgentRunResponseUpdates()
    {
        AgentRunResponseUpdate? extra = null;
        if (this.AdditionalProperties is not null || this.Usage is not null)
        {
            extra = new AgentRunResponseUpdate
            {
                AdditionalProperties = this.AdditionalProperties
            };

            if (this.Usage is { } usage)
            {
                extra.Contents.Add(new UsageContent(usage));
            }
        }

        int messageCount = this._messages?.Count ?? 0;
        var updates = new AgentRunResponseUpdate[messageCount + (extra is not null ? 1 : 0)];

        int i;
        for (i = 0; i < messageCount; i++)
        {
            ChatMessage message = this._messages![i];
            updates[i] = new AgentRunResponseUpdate
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

    /// <summary>
    /// Deserializes the response text into the given type using the specified serializer options.
    /// </summary>
    /// <typeparam name="T">The output type to deserialize into.</typeparam>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <returns>The result as the requested type.</returns>
    /// <exception cref="InvalidOperationException">The result is not parsable into the requested type.</exception>
    public T Deserialize<T>(JsonSerializerOptions serializerOptions)
    {
        _ = Throw.IfNull(serializerOptions);

        var structuredOutput = this.GetResultCore<T>(serializerOptions, out var failureReason);
        return failureReason switch
        {
            FailureReason.ResultDidNotContainJson => throw new InvalidOperationException("The response did not contain JSON to be deserialized."),
            FailureReason.DeserializationProducedNull => throw new InvalidOperationException("The deserialized response is null."),
            _ => structuredOutput!,
        };
    }

    /// <summary>
    /// Tries to deserialize response text into the given type using the specified serializer options.
    /// </summary>
    /// <typeparam name="T">The output type to deserialize into.</typeparam>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="structuredOutput">The parsed structured output.</param>
    /// <returns><see langword="true" /> if parsing was successful; otherwise, <see langword="false" />.</returns>
    public bool TryDeserialize<T>(JsonSerializerOptions serializerOptions, [NotNullWhen(true)] out T? structuredOutput)
    {
        _ = Throw.IfNull(serializerOptions);

        try
        {
            structuredOutput = this.GetResultCore<T>(serializerOptions, out var failureReason);
            return failureReason is null;
        }
        catch
        {
            structuredOutput = default;
            return false;
        }
    }

    private static T? DeserializeFirstTopLevelObject<T>(string json, JsonTypeInfo<T> typeInfo)
    {
#if NET9_0_OR_GREATER
        // We need to deserialize only the first top-level object as a workaround for a common LLM backend
        // issue. GPT 3.5 Turbo commonly returns multiple top-level objects after doing a function call.
        // See https://community.openai.com/t/2-json-objects-returned-when-using-function-calling-and-json-mode/574348
        var utf8ByteLength = Encoding.UTF8.GetByteCount(json);
        var buffer = ArrayPool<byte>.Shared.Rent(utf8ByteLength);
        try
        {
            var utf8SpanLength = Encoding.UTF8.GetBytes(json, 0, json.Length, buffer, 0);
            var reader = new Utf8JsonReader(new ReadOnlySpan<byte>(buffer, 0, utf8SpanLength), new() { AllowMultipleValues = true });
            return JsonSerializer.Deserialize(ref reader, typeInfo);
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
#else
        return JsonSerializer.Deserialize(json, typeInfo);
#endif
    }

    private T? GetResultCore<T>(JsonSerializerOptions serializerOptions, out FailureReason? failureReason)
    {
        var json = this.Text;
        if (string.IsNullOrEmpty(json))
        {
            failureReason = FailureReason.ResultDidNotContainJson;
            return default;
        }

        // If there's an exception here, we want it to propagate, since the Result property is meant to throw directly

        T? deserialized = DeserializeFirstTopLevelObject(json!, (JsonTypeInfo<T>)serializerOptions.GetTypeInfo(typeof(T)));

        if (deserialized is null)
        {
            failureReason = FailureReason.DeserializationProducedNull;
            return default;
        }

        failureReason = default;
        return deserialized;
    }

    private enum FailureReason
    {
        ResultDidNotContainJson,
        DeserializationProducedNull
    }
}
