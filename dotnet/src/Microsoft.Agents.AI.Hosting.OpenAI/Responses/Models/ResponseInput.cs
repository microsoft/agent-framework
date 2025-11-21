// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents the input to a response request, which can be either a simple string or a list of messages.
/// </summary>
[JsonConverter(typeof(ResponseInputJsonConverter))]
internal sealed class ResponseInput : IEquatable<ResponseInput>
{
    private ResponseInput(string text)
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
        this.Messages = null;
    }

    private ResponseInput(List<InputMessage> messages)
    {
        this.Messages = messages ?? throw new ArgumentNullException(nameof(messages));
        this.Text = null;
    }

    /// <summary>
    /// Creates a ResponseInput from a text string.
    /// </summary>
    public static ResponseInput FromText(string text) => new(text);

    /// <summary>
    /// Creates a ResponseInput from a list of messages.
    /// </summary>
    public static ResponseInput FromMessages(List<InputMessage> messages) => new(messages);

    /// <summary>
    /// Creates a ResponseInput from a list of messages.
    /// </summary>
    public static ResponseInput FromMessages(params InputMessage[] messages) => new(messages.ToList());

    /// <summary>
    /// Implicit conversion from string to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(string text) => FromText(text);

    /// <summary>
    /// Implicit conversion from InputMessage array to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(InputMessage[] messages) => FromMessages(messages);

    /// <summary>
    /// Implicit conversion from List to ResponseInput.
    /// </summary>
    public static implicit operator ResponseInput(List<InputMessage> messages) => FromMessages(messages);

    /// <summary>
    /// Gets whether this input is a text string.
    /// </summary>
    public bool IsText => this.Text is not null;

    /// <summary>
    /// Gets whether this input is a list of messages.
    /// </summary>
    public bool IsMessages => this.Messages is not null;

    /// <summary>
    /// Gets the text value, or null if this is not a text input.
    /// </summary>
    public string? Text { get; }

    /// <summary>
    /// Gets the messages value, or null if this is not a messages input.
    /// </summary>
    public List<InputMessage>? Messages { get; }

    /// <summary>
    /// Gets the input as a list of InputMessage objects.
    /// </summary>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1024:Use properties where appropriate", Justification = "Method performs transformation logic")]
    public List<InputMessage> GetInputMessages()
    {
        if (this.Text is not null)
        {
            return [new InputMessage
            {
                Role = ChatRole.User,
                Content = this.Text
            }];
        }

        return this.Messages ?? [];
    }

    /// <inheritdoc/>
    public bool Equals(ResponseInput? other)
    {
        if (other is null)
        {
            return false;
        }

        if (ReferenceEquals(this, other))
        {
            return true;
        }

        // Both text
        if (this.Text is not null && other.Text is not null)
        {
            return this.Text == other.Text;
        }

        // Both messages
        if (this.Messages is not null && other.Messages is not null)
        {
            return this.Messages.SequenceEqual(other.Messages);
        }

        // One is text, one is messages - not equal
        return false;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => this.Equals(obj as ResponseInput);

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Text is not null)
        {
            return this.Text.GetHashCode();
        }

        if (this.Messages is not null)
        {
            return this.Messages.Count > 0 ? this.Messages[0].GetHashCode() : 0;
        }

        return 0;
    }

    /// <summary>
    /// Equality operator.
    /// </summary>
    public static bool operator ==(ResponseInput? left, ResponseInput? right)
    {
        return Equals(left, right);
    }

    /// <summary>
    /// Inequality operator.
    /// </summary>
    public static bool operator !=(ResponseInput? left, ResponseInput? right)
    {
        return !Equals(left, right);
    }
}

/// <summary>
/// JSON converter for ResponseInput.
/// </summary>
internal sealed class ResponseInputJsonConverter : JsonConverter<ResponseInput>
{
    /// <inheritdoc/>
    public override ResponseInput? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Check if it's a string
        if (reader.TokenType == JsonTokenType.String)
        {
            var text = reader.GetString();
            return text is not null ? ResponseInput.FromText(text) : null;
        }

        // Check if it's an array
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            var messages = JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ListInputMessage);
            return messages is not null ? ResponseInput.FromMessages(messages) : null;
        }

        throw new JsonException(
            "ResponseInput must be either a string or an array of messages. " +
            $"Objects are not supported. Received token type: {reader.TokenType}");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ResponseInput value, JsonSerializerOptions options)
    {
        if (value.IsText)
        {
            writer.WriteStringValue(value.Text);
        }
        else if (value.IsMessages)
        {
            JsonSerializer.Serialize(writer, value.Messages!, OpenAIHostingJsonContext.Default.ListInputMessage);
        }
        else
        {
            throw new JsonException("ResponseInput has no value");
        }
    }
}
