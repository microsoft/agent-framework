// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

/// <summary>
/// Content which is a part of <see cref="ChatCompletionRequestMessage"/>.
/// Can be either a string, or a list of content parts
/// </summary>
[JsonConverter(typeof(MessageContentJsonConverter))]
internal sealed record MessageContent : IEquatable<MessageContent>
{
    private MessageContent(string text)
    {
        this.Text = text ?? throw new ArgumentNullException(nameof(text));
        this.Contents = null;
    }

    private MessageContent(IReadOnlyList<MessageContentPart> contents)
    {
        this.Contents = contents ?? throw new ArgumentNullException(nameof(contents));
        this.Text = null;
    }

    /// <summary>
    /// Creates an MessageContent from a text string.
    /// </summary>
    public static MessageContent FromText(string text) => new(text);

    /// <summary>
    /// Creates an MessageContent from a list of MessageContentPart items.
    /// </summary>
    public static MessageContent FromContents(IReadOnlyList<MessageContentPart> contents) => new(contents);

    /// <summary>
    /// Creates an MessageContent from a list of MessageContentPart items.
    /// </summary>
    public static MessageContent FromContents(params MessageContentPart[] contents) => new(contents);

    /// <summary>
    /// Implicit conversion from string to MessageContent.
    /// </summary>
    public static implicit operator MessageContent(string text) => FromText(text);

    /// <summary>
    /// Implicit conversion from List to MessageContent.
    /// </summary>
    public static implicit operator MessageContent(List<MessageContentPart> contents) => FromContents(contents);

    /// <summary>
    /// Gets whether this content is text.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Text))]
    public bool IsText => this.Text is not null;

    /// <summary>
    /// Gets whether this content is a list of ItemContent items.
    /// </summary>
    [MemberNotNullWhen(true, nameof(Contents))]
    public bool IsContents => this.Contents is not null;

    /// <summary>
    /// Gets the text value, or null if this is not text content.
    /// </summary>
    public string? Text { get; }

    /// <summary>
    /// Gets the ItemContent items, or null if this is not a content list.
    /// </summary>
    public IReadOnlyList<MessageContentPart>? Contents { get; }

    /// <inheritdoc/>
    public bool Equals(MessageContent? other)
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

        // Both contents
        if (this.Contents is not null
            && other.Contents is not null
            && this.Contents.Count == other.Contents.Count)
        {
            return this.Contents.SequenceEqual(other.Contents);
        }

        // One is text, one is contents - not equal
        return false;
    }

    /// <inheritdoc/>
    public override int GetHashCode()
    {
        if (this.Text is not null)
        {
            return this.Text.GetHashCode();
        }

        if (this.Contents is not null)
        {
            return this.Contents.Count > 0 ? this.Contents[0].GetHashCode() : 0;
        }

        return 0;
    }
}

/// <summary>
/// JSON converter for <see cref="MessageContent"/>.
/// </summary>
internal sealed class MessageContentJsonConverter : JsonConverter<MessageContent>
{
    public override MessageContent? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Check if it's a string
        if (reader.TokenType == JsonTokenType.String)
        {
            var text = reader.GetString();
            return text is not null ? MessageContent.FromText(text) : null;
        }

        // Check if it's an array of ItemContent
        if (reader.TokenType == JsonTokenType.StartArray)
        {
            var contents = JsonSerializer.Deserialize(ref reader, ChatCompletionsJsonContext.Default.IReadOnlyListMessageContentPart);
            return contents?.Count > 0
                ? MessageContent.FromContents(contents)
                : MessageContent.FromText(string.Empty);
        }

        throw new JsonException($"Unexpected token type for MessageContent: {reader.TokenType}");
    }

    public override void Write(Utf8JsonWriter writer, MessageContent value, JsonSerializerOptions options)
    {
        if (value.IsText)
        {
            writer.WriteStringValue(value.Text);
        }
        else if (value.IsContents)
        {
            JsonSerializer.Serialize(writer, value.Contents, ChatCompletionsJsonContext.Default.IReadOnlyListMessageContentPart);
        }
        else
        {
            throw new JsonException("MessageContent has no value");
        }
    }
}
